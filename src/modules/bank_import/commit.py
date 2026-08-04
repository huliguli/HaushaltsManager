"""Bank-statement commit routing (Qt-free, so it is unit-testable).

Decides, per parsed transaction, whether it is a one-off income (a bank credit
booked only to its statement month) or a dated one-off expense, writes it to the
right repository, learns the payee -> category rule, and logs the transaction
hash for de-duplication. Extracted from the import view precisely because this
is the routing the v1.7.1 "inflated income" bug lived in: keeping it out of Qt
lets a regression test pin the behaviour down (imported credit must land in
variable_income for its booking month only, never as a recurring income source).
"""

from __future__ import annotations

from modules import dates
from modules.bank_import.model import normalize, transaction_hash
from modules.models import VariableExpense, VariableIncome


def commit_transactions(
    transactions, expense_repo, var_income_repo, rule_repo, log_repo,
    today_iso: str | None = None, batch_id: str | None = None,
) -> tuple[int, int]:
    """Write confirmed transactions; return ``(n_expenses, n_income)``.

    Idempotent across re-imports only insofar as the caller has already dropped
    known hashes; this function additionally records each hash so a *later*
    re-import of the same statement is de-duplicated. When a ``batch_id`` is
    given, every log row also records which row the commit created — that is
    what :func:`rollback_batch` replays to undo the whole import.
    """
    today_iso = today_iso or dates.to_iso(dates.today())
    n_exp = n_inc = 0
    # Two genuinely identical bookings (same day, amount and payee — normal for
    # PDF/CSV statements) share one transaction_hash. The log's UNIQUE(tx_hash)
    # plus INSERT OR IGNORE then kept only ONE row for two created bookings, so
    # "Import rückgängig" removed only one of them. Numbering repeats within the
    # batch restores a 1:1 mapping without touching the schema; de-duplication
    # still works because the FIRST occurrence keeps the plain hash.
    seen_hashes: dict[str, int] = {}
    for t in transactions:
        if t.is_income:
            # Imported credits are ONE-OFF income, booked to their statement
            # month — NOT a recurring income source. A single transfer (someone
            # paying you back) must never inflate the ongoing monthly income; it
            # counts only in its month (see budget.compute_overview).
            created_id = var_income_repo.add(VariableIncome(
                date=t.booking_date or today_iso, amount_cents=t.abs_cents,
                source=(t.payee or t.purpose or "Einnahme")[:80]))
            created_kind = "income"
            n_inc += 1
        else:
            # Imported expenses are one-off, dated to their actual booking month.
            # recurring=False on purpose: an imported item must never be carried
            # into the next month, become a fixed cost or feed the fixed-cost
            # timeline — only user-defined fixed costs recur.
            created_id = expense_repo.add(VariableExpense(
                date=t.booking_date or today_iso, amount_cents=t.abs_cents,
                category=t.category or "Sonstiges",
                description=(t.payee or t.purpose or "")[:120],
                recurring=False))
            created_kind = "expense"
            n_exp += 1
            if t.payee:  # learn: this payee -> this category for next time
                rule_repo.upsert(
                    normalize(t.payee), t.category or "Sonstiges", learned=True)
        base_hash = transaction_hash(t)
        seen_hashes[base_hash] = seen_hashes.get(base_hash, 0) + 1
        occurrence = seen_hashes[base_hash]
        tx_hash = base_hash if occurrence == 1 else f"{base_hash}#{occurrence}"
        log_repo.add(tx_hash, t.booking_date, t.amount_cents,
                     batch_id=batch_id, created_kind=created_kind,
                     created_row_id=created_id)
    return n_exp, n_inc


def rollback_batch(batch_id: str, expense_repo, var_income_repo, log_repo) -> tuple[int, int]:
    """Undo one committed import: delete every row it created, then drop the
    batch's log rows (incl. hashes, so a re-import is possible again).

    Rows the user already deleted by hand simply no longer exist — deleting
    them again is a harmless no-op. Learned categorisation rules are kept on
    purpose: they reflect the user's confirmed mapping, not the bookings.
    Returns ``(n_expenses, n_income)`` removed.
    """
    n_exp = n_inc = 0
    for row in log_repo.rows_for_batch(batch_id):
        kind, rid = row["created_kind"], row["created_row_id"]
        if rid is None:
            continue
        if kind == "expense":
            expense_repo.delete(rid)
            n_exp += 1
        elif kind == "income":
            var_income_repo.delete(rid)
            n_inc += 1
    log_repo.delete_batch(batch_id)
    return n_exp, n_inc

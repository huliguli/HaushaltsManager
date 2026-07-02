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
    today_iso: str | None = None,
) -> tuple[int, int]:
    """Write confirmed transactions; return ``(n_expenses, n_income)``.

    Idempotent across re-imports only insofar as the caller has already dropped
    known hashes; this function additionally records each hash so a *later*
    re-import of the same statement is de-duplicated.
    """
    today_iso = today_iso or dates.to_iso(dates.today())
    n_exp = n_inc = 0
    for t in transactions:
        if t.is_income:
            # Imported credits are ONE-OFF income, booked to their statement
            # month — NOT a recurring income source. A single transfer (someone
            # paying you back) must never inflate the ongoing monthly income; it
            # counts only in its month (see budget.compute_overview).
            var_income_repo.add(VariableIncome(
                date=t.booking_date or today_iso, amount_cents=t.abs_cents,
                source=(t.payee or t.purpose or "Einnahme")[:80]))
            n_inc += 1
        else:
            # Imported expenses are one-off, dated to their actual booking month.
            # recurring=False on purpose: an imported item must never be carried
            # into the next month, become a fixed cost or feed the fixed-cost
            # timeline — only user-defined fixed costs recur.
            expense_repo.add(VariableExpense(
                date=t.booking_date or today_iso, amount_cents=t.abs_cents,
                category=t.category or "Sonstiges",
                description=(t.payee or t.purpose or "")[:120],
                recurring=False))
            n_exp += 1
            if t.payee:  # learn: this payee -> this category for next time
                rule_repo.upsert(
                    normalize(t.payee), t.category or "Sonstiges", learned=True)
        log_repo.add(transaction_hash(t), t.booking_date, t.amount_cents)
    return n_exp, n_inc

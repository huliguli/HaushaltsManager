"""Regression test for the bank-import commit routing (the v1.7.1 bug).

An imported credit must land in variable_income for its booking month only and
must NEVER become a recurring income source; re-committing the same statement
must add nothing (de-dup). This routing used to live inside the Qt view and was
untested — the exact place the "6924 EUR of phantom income" bug came from.
"""

from modules import budget
from modules.bank_import.commit import commit_transactions
from modules.bank_import.model import BankTransaction
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    FixedCostRepository,
    ImportLogRepository,
    ImportRuleRepository,
    IncomeRepository,
    VariableExpenseRepository,
    VariableIncomeRepository,
)


def _repos(tmp_path):
    db = Database(tmp_path / "commit.db")
    return (db, IncomeRepository(db), FixedCostRepository(db),
            VariableExpenseRepository(db), VariableIncomeRepository(db),
            ImportRuleRepository(db), ImportLogRepository(db))


def _dedup(transactions, log):
    from modules.bank_import.model import transaction_hash
    hashes = [transaction_hash(t) for t in transactions]
    known = log.known(hashes)
    return [t for t, h in zip(transactions, hashes) if h not in known]


def test_credit_is_one_off_income_not_recurring(tmp_path):
    db, income, fixed, exp, var_income, rules, log = _repos(tmp_path)
    txs = [
        BankTransaction(booking_date="2026-06-03", amount_cents=-4_299, payee="ARAL",
                        category="Auto & Tanken"),
        BankTransaction(booking_date="2026-06-10", amount_cents=50_000, payee="Max Mustermann",
                        purpose="Rueckzahlung"),
    ]
    n_exp, n_inc = commit_transactions(txs, exp, var_income, rules, log)
    assert (n_exp, n_inc) == (1, 1)

    # The credit is a one-off in its month, NOT a recurring income source.
    assert var_income.total_for_month(2026, 6) == 50_000
    assert income.total_active() == 0                     # income_sources untouched
    # compute_overview counts it only in June, never carried into July.
    jun = budget.compute_overview(income, fixed, exp, 2026, 6, var_income_repo=var_income)
    jul = budget.compute_overview(income, fixed, exp, 2026, 7, var_income_repo=var_income)
    assert jun.income_cents == 50_000 and jul.income_cents == 0
    # The expense was learned as a rule and dated to its booking month.
    assert ("aral", "Auto & Tanken") in rules.rules()
    assert exp.total_for_month(2026, 6) == 4_299
    db.close()


def test_reimport_same_statement_is_deduped(tmp_path):
    db, income, fixed, exp, var_income, rules, log = _repos(tmp_path)
    txs = [
        BankTransaction(booking_date="2026-06-03", amount_cents=-4_299, payee="ARAL",
                        category="Auto & Tanken"),
        BankTransaction(booking_date="2026-06-10", amount_cents=50_000, payee="Max"),
    ]
    commit_transactions(_dedup(txs, log), exp, var_income, rules, log)
    # Second run of the identical statement: everything is already known.
    fresh = _dedup(txs, log)
    assert fresh == []
    n_exp, n_inc = commit_transactions(fresh, exp, var_income, rules, log)
    assert (n_exp, n_inc) == (0, 0)
    assert exp.total_for_month(2026, 6) == 4_299          # not doubled
    assert var_income.total_for_month(2026, 6) == 50_000
    db.close()

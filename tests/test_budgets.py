"""Tests for category budgets and the full-data reset (wipe)."""

from datetime import date

from modules import budget
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    CategoryBudgetRepository,
    FixedCostRepository,
    ImportLogRepository,
    IncomeRepository,
    VariableExpenseRepository,
    VariableIncomeRepository,
)
from modules.models import FixedCost, IncomeSource, VariableExpense, VariableIncome


def test_category_budget_set_update_clear(tmp_path):
    db = Database(tmp_path / "budgets.db")
    repo = CategoryBudgetRepository(db)
    repo.set("Lebensmittel", 40_000)
    repo.set("Auto & Tanken", 15_000)
    assert repo.all() == {"Lebensmittel": 40_000, "Auto & Tanken": 15_000}

    repo.set("Lebensmittel", 45_000)                 # upsert in place
    assert repo.all()["Lebensmittel"] == 45_000
    assert len(repo.list()) == 2                     # no duplicate row

    repo.set("Auto & Tanken", 0)                     # <=0 clears the budget
    assert "Auto & Tanken" not in repo.all()
    db.close()


def test_category_budget_table_is_noop_on_existing_db(tmp_path):
    # Opening an already-migrated DB again must not disturb existing budgets
    # (the additive CREATE IF NOT EXISTS is a no-op on the second open).
    path = tmp_path / "reopen.db"
    db = Database(path)
    CategoryBudgetRepository(db).set("Lebensmittel", 30_000)
    db.close()

    db2 = Database(path)
    assert CategoryBudgetRepository(db2).all() == {"Lebensmittel": 30_000}
    db2.close()


def test_wipe_clears_every_financial_table(tmp_path):
    # "Alle Daten löschen" must leave nothing behind — including one-off income
    # and the bank-import log (the CONFIRMED v1.7.1-class bug: variable_income
    # survived the old wipe and kept inflating income after a full reset).
    db = Database(tmp_path / "wipe.db")
    income = IncomeRepository(db)
    fixed = FixedCostRepository(db)
    exp = VariableExpenseRepository(db)
    var_income = VariableIncomeRepository(db)
    log = ImportLogRepository(db)
    budgets = CategoryBudgetRepository(db)

    income.add(IncomeSource("Job", 200_000, "teilzeit"))
    fixed.add(FixedCost("Miete", 80_000, "Wohnen"))
    exp.add(VariableExpense("2026-06-05", 3_000, "Lebensmittel"))
    var_income.add(VariableIncome("2026-06-10", 50_000, "Rückzahlung"))
    log.add("hash-1", "2026-06-10", 50_000)
    budgets.set("Lebensmittel", 40_000)

    db.wipe_financial_data()

    ov = budget.compute_overview(income, fixed, exp, 2026, 6, var_income_repo=var_income)
    assert ov.income_cents == 0 and ov.fixed_cents == 0 and ov.variable_cents == 0
    assert var_income.total_for_month(2026, 6) == 0        # one-off income gone
    assert budgets.all() == {}                             # budgets gone
    assert log.known(["hash-1"]) == set()                  # dedup log cleared -> re-import works
    db.close()

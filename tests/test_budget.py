"""Tests for the budget aggregator (compute_overview, month_bounds).

compute_overview is the most important number in the app (the dashboard's
income / fixed / variable / credits split); it had no test before.
"""

from modules import budget
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    FixedCostRepository,
    IncomeRepository,
    VariableExpenseRepository,
)
from modules.models import FixedCost, IncomeSource, VariableExpense


def _repos(tmp_path):
    db = Database(tmp_path / "budget.db")
    return db, IncomeRepository(db), FixedCostRepository(db), VariableExpenseRepository(db)


def test_month_bounds_handles_month_lengths():
    assert budget.month_bounds(2026, 6) == ("2026-06-01", "2026-06-30")
    assert budget.month_bounds(2024, 2) == ("2024-02-01", "2024-02-29")  # leap year
    assert budget.month_bounds(2026, 2) == ("2026-02-01", "2026-02-28")
    assert budget.month_bounds(2026, 12) == ("2026-12-01", "2026-12-31")


def test_compute_overview_splits_credits_and_month(tmp_path):
    db, income, fixed, expenses = _repos(tmp_path)
    income.add(IncomeSource("Job", 200_000, "teilzeit"))
    income.add(IncomeSource("Inaktiv", 99_900, "sonstiges", active=False))
    fixed.add(FixedCost("Miete", 80_000, "Wohnen"))
    fixed.add(FixedCost("Autokredit", 25_000, "Kredit"))
    expenses.add(VariableExpense("2026-06-05", 3_000, "Lebensmittel"))
    expenses.add(VariableExpense("2026-07-01", 9_900, "Freizeit & Unterhaltung"))  # other month

    ov = budget.compute_overview(income, fixed, expenses, 2026, 6)
    assert ov.income_cents == 200_000        # inactive income excluded
    assert ov.fixed_cents == 105_000         # 80000 + 25000
    assert ov.credits_cents == 25_000        # only the "Kredit"-category fixed cost
    assert ov.variable_cents == 3_000        # July expense excluded
    assert ov.expenses_by_category == {"Lebensmittel": 3_000}
    db.close()


def test_compute_overview_one_time_income_only_in_its_month(tmp_path):
    # An imported credit counts in its booking month but never inflates the
    # ongoing monthly income (regression for the "all income in current month").
    from modules.db_handler.repositories import VariableIncomeRepository
    from modules.models import VariableIncome
    db, income, fixed, expenses = _repos(tmp_path)
    var_income = VariableIncomeRepository(db)
    income.add(IncomeSource("Job", 180_000, "teilzeit"))
    var_income.add(VariableIncome("2026-05-15", 205_000, "Mai-Gutschriften"))

    may = budget.compute_overview(income, fixed, expenses, 2026, 5, var_income_repo=var_income)
    jul = budget.compute_overview(income, fixed, expenses, 2026, 7, var_income_repo=var_income)
    assert may.income_cents == 385_000     # recurring + one-off May
    assert jul.income_cents == 180_000     # one-off NOT carried into July
    # The forward-projection figure stays recurring-only in both months.
    assert may.recurring_income_cents == 180_000
    assert jul.recurring_income_cents == 180_000
    db.close()


def test_recurring_after_properties_ignore_one_off_income(tmp_path):
    # The recurring_after_* properties power long-term decisions (annual saving
    # projection, car/savings feasibility): a one-off credit must not lift them.
    from modules.db_handler.repositories import VariableIncomeRepository
    from modules.models import VariableIncome
    db, income, fixed, expenses = _repos(tmp_path)
    var_income = VariableIncomeRepository(db)
    income.add(IncomeSource("Job", 200_000, "teilzeit"))
    fixed.add(FixedCost("Miete", 80_000, "Wohnen"))
    expenses.add(VariableExpense("2026-06-05", 5_000, "Lebensmittel"))
    var_income.add(VariableIncome("2026-06-10", 300_000, "Einmal-Gutschrift"))

    ov = budget.compute_overview(income, fixed, expenses, 2026, 6, var_income_repo=var_income)
    # after_all reflects the fat one-off month; recurring_after_all does NOT.
    assert ov.after_all_cents == 500_000 - 80_000 - 5_000
    assert ov.recurring_after_fixed_cents == 200_000 - 80_000
    assert ov.recurring_after_all_cents == 200_000 - 80_000 - 5_000
    db.close()


def test_compute_overview_materialises_recurring(tmp_path):
    # The recurring path of compute_overview: a recurring variable expense that
    # started in an earlier month is materialised into the requested month and
    # summed alongside this month's one-off spending.
    db, income, fixed, expenses = _repos(tmp_path)
    expenses.add(VariableExpense("2026-05-15", 4_000, "Streaming & Abos", recurring=True))
    expenses.add(VariableExpense("2026-06-05", 3_000, "Lebensmittel"))

    ov = budget.compute_overview(income, fixed, expenses, 2026, 6)
    assert ov.variable_cents == 7_000        # 3000 one-off + 4000 recurring
    assert ov.expenses_by_category == {"Streaming & Abos": 4_000, "Lebensmittel": 3_000}
    db.close()

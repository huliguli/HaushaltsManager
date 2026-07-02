"""Tests for the monthly history/trend series and the snapshot cache."""

from datetime import date

from modules import history
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    FixedCostRepository,
    IncomeRepository,
    MonthlySummaryRepository,
    VariableExpenseRepository,
    VariableIncomeRepository,
)
from modules.models import FixedCost, IncomeSource, MonthlySummary, VariableExpense


def _repos(tmp_path):
    db = Database(tmp_path / "hist.db")
    return (db, IncomeRepository(db), FixedCostRepository(db),
            VariableExpenseRepository(db), VariableIncomeRepository(db),
            MonthlySummaryRepository(db))


def test_monthly_series_shape_and_values(tmp_path):
    db, income, fixed, exp, var_income, summ = _repos(tmp_path)
    income.add(IncomeSource("Job", 200_000, "teilzeit"))
    fixed.add(FixedCost("Miete", 80_000, "Wohnen"))
    exp.add(VariableExpense("2026-05-10", 3_000, "Lebensmittel"))
    exp.add(VariableExpense("2026-06-05", 5_000, "Auto & Tanken"))

    points = history.monthly_series(
        income, fixed, exp, var_income, summ, months=3, ref=date(2026, 6, 15))
    assert [(p.year, p.month) for p in points] == [(2026, 4), (2026, 5), (2026, 6)]
    may, jun = points[1], points[2]
    assert may.variable_cents == 3_000 and jun.variable_cents == 5_000
    assert jun.income_cents == 200_000 and jun.fixed_cents == 80_000
    assert jun.remaining_cents == 200_000 - 80_000 - 5_000
    assert points[2].label == "Jun 2026"
    db.close()


def test_series_persists_completed_months_but_not_current(tmp_path):
    db, income, fixed, exp, var_income, summ = _repos(tmp_path)
    income.add(IncomeSource("Job", 100_000, "teilzeit"))
    exp.add(VariableExpense("2026-05-10", 2_000, "Lebensmittel"))

    ref = date(2026, 6, 15)
    history.monthly_series(income, fixed, exp, var_income, summ, months=3, ref=ref)
    # May (completed) is snapshotted; June (current) is not frozen.
    may = summ.get(2026, 5)
    assert may is not None and may.variable_cents == 2_000
    assert summ.get(2026, 6) is None


def test_snapshot_matches_live_compute_overview(tmp_path):
    from modules import budget
    db, income, fixed, exp, var_income, summ = _repos(tmp_path)
    income.add(IncomeSource("Job", 175_000, "teilzeit"))
    fixed.add(FixedCost("Miete", 60_000, "Wohnen"))
    exp.add(VariableExpense("2026-05-10", 4_200, "Lebensmittel"))

    history.monthly_series(income, fixed, exp, var_income, summ, months=2, ref=date(2026, 6, 1))
    snap = summ.get(2026, 5)
    live = budget.compute_overview(income, fixed, exp, 2026, 5, var_income_repo=var_income)
    assert snap.income_cents == live.income_cents
    assert snap.fixed_cents == live.fixed_cents
    assert snap.variable_cents == live.variable_cents
    assert snap.remaining_cents == live.after_all_cents
    db.close()


def test_monthly_summary_upsert_is_unique_per_month(tmp_path):
    db = Database(tmp_path / "sum.db")
    summ = MonthlySummaryRepository(db)
    summ.upsert(MonthlySummary(2026, 6, income_cents=100_000, remaining_cents=10_000))
    summ.upsert(MonthlySummary(2026, 6, income_cents=120_000, remaining_cents=20_000))
    rows = summ.list()
    assert len(rows) == 1                        # UNIQUE(year, month) -> single row
    assert rows[0].income_cents == 120_000       # updated in place
    assert summ.get(2026, 6).remaining_cents == 20_000
    db.close()


def test_category_series_folds_rest_and_aligns(tmp_path):
    p1 = history.MonthPoint(2026, 5, by_category={"A": 100, "B": 50, "C": 10, "D": 5})
    p2 = history.MonthPoint(2026, 6, by_category={"A": 80, "B": 60})
    labels, per_month = history.category_series([p1, p2], top_n=2)
    assert labels == ["A", "B", "Übrige"]
    assert per_month["A"] == [100, 80]
    assert per_month["B"] == [50, 60]
    assert per_month["Übrige"] == [15, 0]        # C+D folded in May, none in June

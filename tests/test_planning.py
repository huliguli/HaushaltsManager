"""Tests for planning a savings plan / loan into the Haushaltsbuch (+ undo)."""

import calendar
from datetime import date

from modules import budget, dates, planning
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    CreditRepository,
    FixedCostRepository,
    IncomeRepository,
    VariableExpenseRepository,
)


def _active_in(fixed_repo, fixed_id, year, month):
    last = calendar.monthrange(year, month)[1]
    start, end = f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"
    return any(c.id == fixed_id for c in fixed_repo.active_for_month(start, end))


def _repos(tmp_path):
    db = Database(tmp_path / "plan.db")
    return db, FixedCostRepository(db), CreditRepository(db)


def test_term_end_iso_is_inclusive_last_month():
    # A 24-month term starting July 2026 runs through (and including) June 2028.
    assert planning.term_end_iso(date(2026, 7, 15), 24) == "2028-06-30"
    assert planning.term_end_iso(date(2026, 1, 1), 12) == "2026-12-31"
    assert planning.term_end_iso(date(2026, 7, 1), 1) == "2026-07-31"


def test_plan_savings_creates_bounded_fixed_cost(tmp_path):
    db, fixed, _credits = _repos(tmp_path)
    fid = planning.plan_savings(fixed, 20_000, 24, start=date(2026, 7, 15))
    fc = fixed.get(fid)
    assert fc.category == "Sparen" and fc.amount_cents == 20_000 and fc.active
    assert fc.end_date == "2028-06-30"
    # Active during the term, inactive after it.
    assert any(c.id == fid for c in fixed.active_for_month("2026-07-01", "2026-07-31"))
    assert any(c.id == fid for c in fixed.active_for_month("2028-06-01", "2028-06-30"))
    assert not any(c.id == fid for c in fixed.active_for_month("2028-07-01", "2028-07-31"))
    # Undo removes it entirely.
    planning.unplan_savings(fixed, fid)
    assert fixed.get(fid) is None
    db.close()


def test_plan_savings_future_start_hits_exactly_the_right_months(tmp_path):
    # Start 2 months out (Sept 2026) for 6 months -> Sep 2026 .. Feb 2027.
    db, fixed, _credits = _repos(tmp_path)
    fid = planning.plan_savings(fixed, 10_000, 6, start=date(2026, 9, 1))
    fc = fixed.get(fid)
    assert fc.start_date == "2026-09-01" and fc.end_date == "2027-02-28"

    assert not _active_in(fixed, fid, 2026, 7)     # this month (before start) — untouched
    assert not _active_in(fixed, fid, 2026, 8)     # next month — untouched
    assert _active_in(fixed, fid, 2026, 9)         # start month
    assert _active_in(fixed, fid, 2027, 2)         # final month of the term
    assert not _active_in(fixed, fid, 2027, 3)     # after the term — untouched
    # Exactly six consecutive months are affected.
    affected = sum(_active_in(fixed, fid, *dates.shift_month(2026, 9, i)) for i in range(0, 8))
    assert affected == 6
    db.close()


def test_future_savings_counts_in_budget_only_within_term(tmp_path):
    db, fixed, _credits = _repos(tmp_path)
    income = IncomeRepository(db)
    exp = VariableExpenseRepository(db)
    planning.plan_savings(fixed, 10_000, 6, start=date(2026, 9, 1))
    assert budget.compute_overview(income, fixed, exp, 2026, 7).fixed_cents == 0    # before start
    assert budget.compute_overview(income, fixed, exp, 2026, 9).fixed_cents == 10_000  # active
    assert budget.compute_overview(income, fixed, exp, 2027, 2).fixed_cents == 10_000  # last month
    assert budget.compute_overview(income, fixed, exp, 2027, 3).fixed_cents == 0    # after end
    db.close()


def test_plan_savings_counts_in_budget(tmp_path):
    db, fixed, _credits = _repos(tmp_path)
    income = IncomeRepository(db)
    exp = VariableExpenseRepository(db)
    planning.plan_savings(fixed, 15_000, 12, start=date(2026, 7, 1))
    ov = budget.compute_overview(income, fixed, exp, 2026, 7)
    assert ov.fixed_cents == 15_000          # the savings rate is planned in
    assert ov.credits_cents == 0             # savings is NOT a credit
    db.close()


def test_plan_credit_creates_credit_and_linked_fixed(tmp_path):
    db, fixed, credits = _repos(tmp_path)
    cid, fid = planning.plan_credit(
        credits, fixed, name="Autokredit", total_cents=3_000_000, monthly_cents=56_000,
        term_months=60, interest_rate=4.9, category="Auto", start=date(2026, 7, 15))
    cr = credits.get(cid)
    fc = fixed.get(fid)
    # Credit carries the full figures and is wired to the fixed cost.
    assert cr.monthly_cents == 56_000 and cr.total_cents == 3_000_000
    assert cr.term_months == 60 and cr.interest_rate == 4.9 and cr.category == "Auto"
    assert cr.linked_fixed_cost_id == fid and cr.status == "aktiv"
    # Linked fixed cost counts as a credit instalment in the budget.
    assert fc.category == "Kredit" and fc.amount_cents == 56_000
    assert fc.end_date == "2031-06-30"

    income = IncomeRepository(db)
    exp = VariableExpenseRepository(db)
    ov = budget.compute_overview(income, fixed, exp, 2026, 8)
    assert ov.fixed_cents == 56_000 and ov.credits_cents == 56_000
    db.close()


def test_unplan_credit_removes_both_rows(tmp_path):
    db, fixed, credits = _repos(tmp_path)
    cid, fid = planning.plan_credit(
        credits, fixed, name="Hausdarlehen", total_cents=28_000_000, monthly_cents=120_000,
        term_months=360, interest_rate=3.6, category="Haus", start=date(2026, 7, 1))
    assert credits.get(cid) is not None and fixed.get(fid) is not None
    planning.unplan_credit(credits, fixed, cid)
    assert credits.get(cid) is None      # credit gone
    assert fixed.get(fid) is None        # linked fixed cost gone too
    db.close()

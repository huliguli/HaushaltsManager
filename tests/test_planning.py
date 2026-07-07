"""Tests for planning a savings plan / loan into the Haushaltsbuch (+ undo)."""

from datetime import date

from modules import budget, planning
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    CreditRepository,
    FixedCostRepository,
    IncomeRepository,
    VariableExpenseRepository,
)


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

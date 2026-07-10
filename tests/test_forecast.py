"""Tests for the forward projection (modules.forecast) and the credit
repayment progress (modules.credit_progress)."""

from datetime import date

from modules import credit_progress, forecast
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    FixedCostRepository,
    IncomeRepository,
    VariableExpenseRepository,
)
from modules.models import Credit, FixedCost, IncomeSource, VariableExpense

REF = date(2026, 7, 15)


def _repos(tmp_path):
    db = Database(tmp_path / "test.db")
    return (db, IncomeRepository(db), FixedCostRepository(db),
            VariableExpenseRepository(db))


def test_fixed_cost_dropoff_lands_in_the_right_month(tmp_path):
    db, income, fixed, exp = _repos(tmp_path)
    income.add(IncomeSource("Job", 250_000, "vollzeit"))
    fixed.add(FixedCost("Miete", 90_000, "Wohnen"))                    # open-ended
    fixed.add(FixedCost("Autokredit", 25_000, "Kredit", end_date="2026-09-30"))

    points = forecast.project(income, fixed, exp, months=4, ref=REF)
    by_month = {(p.year, p.month): p for p in points}
    assert by_month[(2026, 8)].fixed_cents == 115_000    # both still active
    assert by_month[(2026, 9)].fixed_cents == 115_000    # last credit month
    assert by_month[(2026, 10)].fixed_cents == 90_000    # credit dropped off
    assert by_month[(2026, 10)].events == ["Autokredit fällt weg"]
    assert by_month[(2026, 11)].events == []
    # Balance improves exactly by the dropped rate.
    assert (by_month[(2026, 10)].remaining_cents
            - by_month[(2026, 9)].remaining_cents) == 25_000
    db.close()


def test_only_recurring_income_is_projected(tmp_path):
    db, income, fixed, exp = _repos(tmp_path)
    income.add(IncomeSource("Job", 200_000, "vollzeit"))
    income.add(IncomeSource("Inaktiv", 99_000, "sonstiges", active=False))
    points = forecast.project(income, fixed, exp, months=2, ref=REF)
    assert all(p.income_cents == 200_000 for p in points)
    db.close()


def test_recurring_expense_cadence_feeds_the_forecast(tmp_path):
    db, income, fixed, exp = _repos(tmp_path)
    income.add(IncomeSource("Job", 200_000, "vollzeit"))
    exp.add(VariableExpense(date="2026-01-10", amount_cents=30_000,
                            category="Versicherung", recurring=True,
                            interval_months=3))  # Jan, Apr, Jul, Okt ...
    points = forecast.project(income, fixed, exp, months=4, ref=REF)
    by_month = {(p.year, p.month): p.variable_cents for p in points}
    assert by_month[(2026, 10)] >= 30_000                 # quarter month
    assert by_month[(2026, 8)] == by_month[(2026, 9)]     # between quarters
    assert by_month[(2026, 10)] - by_month[(2026, 9)] == 30_000
    db.close()


def test_cumulative_is_running_sum(tmp_path):
    db, income, fixed, exp = _repos(tmp_path)
    income.add(IncomeSource("Job", 100_000, "vollzeit"))
    fixed.add(FixedCost("Miete", 40_000, "Wohnen"))
    points = forecast.project(income, fixed, exp, months=3, ref=REF)
    running = 0
    for p in points:
        running += p.remaining_cents
        assert p.cumulative_cents == running
    db.close()


def test_scheduled_start_appears_as_event(tmp_path):
    db, income, fixed, exp = _repos(tmp_path)
    income.add(IncomeSource("Job", 200_000, "vollzeit"))
    fixed.add(FixedCost("Sparplan Urlaub", 15_000, "Sparen",
                        start_date="2026-10-01", end_date="2027-09-30"))
    points = forecast.project(income, fixed, exp, months=4, ref=REF)
    by_month = {(p.year, p.month): p for p in points}
    assert by_month[(2026, 9)].fixed_cents == 0
    assert by_month[(2026, 10)].fixed_cents == 15_000
    assert by_month[(2026, 10)].events == ["Sparplan Urlaub beginnt"]
    db.close()


# --- credit progress ----------------------------------------------------------

def test_linear_progress_without_interest():
    cr = Credit("Auto", total_cents=1_200_000, monthly_cents=50_000,
                start_date="2026-01-01", term_months=24)
    p = credit_progress.compute(cr, today=date(2026, 6, 15))
    assert p is not None
    assert p.months_total == 24
    assert p.months_elapsed == 6            # Jan..Jun rates due
    assert p.paid_cents == 300_000
    assert p.remaining_cents == 900_000
    assert not p.finished
    assert abs(p.ratio - 0.25) < 1e-9


def test_interest_progress_is_slower_than_linear():
    cr = Credit("Haus", total_cents=1_200_000, monthly_cents=55_000,
                start_date="2026-01-01", term_months=24, interest_rate=6.0)
    p = credit_progress.compute(cr, today=date(2026, 6, 15))
    assert p is not None
    # With interest, part of each rate is interest -> less principal repaid
    # than the linear 6 x 550 EUR.
    assert p.paid_cents < 6 * 55_000
    assert p.remaining_cents > 1_200_000 - 6 * 55_000


def test_finished_credit_shows_full_progress():
    cr = Credit("Alt", total_cents=600_000, monthly_cents=50_000,
                start_date="2020-01-01", term_months=12)
    p = credit_progress.compute(cr, today=date(2026, 7, 10))
    assert p is not None and p.finished
    assert p.remaining_cents == 0 and p.ratio == 1.0


def test_thin_master_data_yields_none():
    assert credit_progress.compute(Credit("Nur Name"), today=REF) is None
    assert credit_progress.compute(
        Credit("Ohne Start", total_cents=100_000, monthly_cents=5_000),
        today=REF) is None

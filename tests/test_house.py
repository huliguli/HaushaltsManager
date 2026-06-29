"""Tests for the mortgage calculator (residual debt after the fixed period)."""

from modules.calculator import house


def test_basic_mortgage():
    res = house.compute(
        price_cents=30_000_000,        # 300,000 €
        equity_cents=6_000_000,        # 60,000 € equity
        annual_rate_pct=3.5,
        fixed_period_years=10,
        term_years=30,
    )
    assert res.loan_cents == 24_000_000
    # Residual after 10 years is below the original loan but above zero.
    assert 0 < res.residual_after_fixed_cents < res.loan_cents
    # Full term amortises to zero.
    assert res.schedule[-1].balance_cents == 0
    # Interest split during the fixed period is consistent.
    assert (res.interest_during_fixed_cents + res.principal_during_fixed_cents
            == sum(r.payment_cents for r in res.schedule[:120]))


def test_residual_matches_schedule():
    res = house.compute(
        price_cents=25_000_000, equity_cents=5_000_000,
        annual_rate_pct=4.0, fixed_period_years=15, term_years=25,
    )
    # Restschuld after the fixed period equals the balance at that month.
    assert res.residual_after_fixed_cents == res.schedule[15 * 12 - 1].balance_cents


def test_fixed_period_longer_than_term():
    # If the loan is fully repaid within the fixed period, residual is zero.
    res = house.compute(
        price_cents=10_000_000, equity_cents=2_000_000,
        annual_rate_pct=3.0, fixed_period_years=20, term_years=10,
    )
    assert res.residual_after_fixed_cents == 0

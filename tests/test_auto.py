"""Tests for the car-financing calculator and its budget feasibility logic."""

from modules.calculator import auto
from modules.calculator.auto import AutoExtras


def test_standard_financing_and_extras():
    res = auto.compute(
        price_cents=3_000_000,        # 30,000 €
        down_payment_cents=500_000,   # 5,000 € down
        annual_rate_pct=4.0,
        term_months=60,
        mode="standard",
        extras=AutoExtras(vollkasko=True, is_electric=False, kfz_steuer=True,
                          tuv_reserve=True, maintenance=True),
        monthly_disposable_cents=80_000,     # 800 € free
        current_auto_fixed_cents=15_000,     # 150 € current car costs
    )
    assert res.principal_cents == 2_500_000
    # Vollkasko = 0.4% of 30,000 € = 120 €
    assert res.extras_breakdown["Vollkasko (0,4 %/Mon.)"] == 12_000
    assert res.extras_breakdown["Kfz-Steuer"] == 1_500
    assert res.monthly_total_cents == res.monthly_financing_cents + res.extras_total_cents
    assert res.available_budget_cents == 95_000  # 800 + 150 freed
    assert res.remaining_after_auto_cents == res.available_budget_cents - res.monthly_total_cents


def test_electric_has_no_kfz_steuer():
    res = auto.compute(
        price_cents=4_000_000, term_months=48, annual_rate_pct=3.0,
        extras=AutoExtras(is_electric=True),
    )
    assert res.extras_breakdown["Kfz-Steuer"] == 0


def test_balloon_adds_reserve_line():
    res = auto.compute(
        price_cents=3_000_000, term_months=48, annual_rate_pct=4.0,
        mode="balloon", balloon_cents=1_200_000,
        extras=AutoExtras(vollkasko=False, kfz_steuer=False,
                          tuv_reserve=False, maintenance=False),
    )
    # Only the balloon reserve remains as an "extra".
    assert "Schlussraten-Rücklage" in res.extras_breakdown
    assert res.extras_breakdown["Schlussraten-Rücklage"] == round(1_200_000 / 48)


def test_feasibility_badges():
    # Comfortable: small instalment vs. large budget.
    good = auto.compute(price_cents=1_000_000, term_months=60, annual_rate_pct=2.0,
                        extras=AutoExtras(False, False, False, False, False),
                        monthly_disposable_cents=200_000)
    assert good.feasibility == "gut"

    # Over budget: high instalment, no income.
    risky = auto.compute(price_cents=6_000_000, term_months=24, annual_rate_pct=8.0,
                         extras=AutoExtras(True, False, True, True, True),
                         monthly_disposable_cents=0)
    assert risky.feasibility == "riskant"
    assert risky.remaining_after_auto_cents < 0

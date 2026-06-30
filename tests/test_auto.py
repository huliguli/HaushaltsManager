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


def test_feasibility_knapp_and_boundaries():
    # The middle "knapp" band and its exact thresholds were never covered.
    assert auto._feasibility(75_000, 100_000) == "gut"      # ratio 0.75 -> still gut
    assert auto._feasibility(90_000, 100_000) == "knapp"    # between 0.75 and 1.0
    assert auto._feasibility(100_000, 100_000) == "knapp"   # ratio 1.0 -> still knapp
    assert auto._feasibility(100_001, 100_000) == "riskant"  # just over budget
    assert auto._feasibility(0, 0) == "gut"                 # no budget, no cost
    assert auto._feasibility(5, 0) == "riskant"             # no budget, some cost


def test_kfz_steuer_combustion_vs_electric_contrast():
    # Pin the differentiator of the is_electric branch as a contrast: a
    # combustion car pays 1500 cents Kfz-Steuer, an electric one pays 0. A
    # regression zeroing the combustion rate would otherwise slip through.
    combustion = auto.compute(price_cents=4_000_000, term_months=48,
                              annual_rate_pct=3.0, extras=AutoExtras(is_electric=False))
    electric = auto.compute(price_cents=4_000_000, term_months=48,
                            annual_rate_pct=3.0, extras=AutoExtras(is_electric=True))
    assert combustion.extras_breakdown["Kfz-Steuer"] == 1_500
    assert electric.extras_breakdown["Kfz-Steuer"] == 0


def test_good_case_financing_amounts():
    # Anchor the annuity instalment in the comfortable case (no extras), which
    # the badge test only checks by label.
    good = auto.compute(price_cents=1_000_000, term_months=60, annual_rate_pct=2.0,
                        extras=AutoExtras(False, False, False, False, False),
                        monthly_disposable_cents=200_000)
    assert good.monthly_financing_cents == 17_528
    assert good.monthly_total_cents == 17_528          # no extras
    assert good.remaining_after_auto_cents == 182_472


def test_extras_override_replaces_defaults():
    # User-edited running-cost amounts are used verbatim (e.g. a larger tyre
    # reserve), instead of the rule-of-thumb defaults.
    override = {"Vollkasko": 14_000, "Kfz-Steuer": 1_500, "TÜV-Rücklage": 800,
                "Wartung": 3_000, "Reifen-Rücklage": 9_000}
    res = auto.compute(price_cents=3_500_000, down_payment_cents=500_000,
                       annual_rate_pct=4.9, term_months=60, extras_override=override,
                       monthly_disposable_cents=91_804)
    assert res.extras_breakdown == override
    assert res.extras_total_cents == 28_300
    assert res.monthly_total_cents == res.monthly_financing_cents + 28_300


def test_extras_override_drops_nonpositive():
    # Zero / negative entries are not counted (an emptied field = cost off).
    res = auto.compute(price_cents=2_000_000, annual_rate_pct=3.0, term_months=48,
                       extras_override={"Vollkasko": 8_000, "Kfz-Steuer": 0,
                                        "Reifen-Rücklage": -5})
    assert res.extras_breakdown == {"Vollkasko": 8_000}
    assert res.extras_total_cents == 8_000


def test_extras_override_keeps_balloon_reserve():
    # The balloon reserve is derived from the financing and always added on top
    # of the user-edited running costs.
    res = auto.compute(price_cents=3_000_000, term_months=48, annual_rate_pct=4.0,
                       mode="balloon", balloon_cents=1_200_000,
                       extras_override={"Vollkasko": 12_000})
    assert "Schlussraten-Rücklage" in res.extras_breakdown
    assert res.extras_breakdown["Vollkasko"] == 12_000

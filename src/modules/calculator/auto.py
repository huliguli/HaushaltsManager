"""Car-financing calculator: standard or balloon plus running costs, then a
feasibility check against the household budget.

The running-cost rules of thumb (all configurable in the UI):
    * Vollkasko       ~0.4 % of the purchase price per month
    * Kfz-Steuer      ~15 € for a combustion car, 0 € for an EV
    * TÜV-Rücklage    ~8 €/month set aside for inspection
    * Wartung/Reifen  ~50 €/month maintenance and tyres

For balloon financing the recommended monthly reserve for the final payment is
added as its own running-cost line, so the budget check reflects the *true*
monthly burden rather than just the (lower) contractual instalment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.calculator import annuity, balloon
from modules.money import round_half_up

# Rules of thumb (cents where fixed, fraction where price-relative).
VOLLKASKO_MONTHLY_RATE = 0.004           # 0.4 % of price per month
KFZ_STEUER_COMBUSTION_CENTS = 1500       # ~15 €
KFZ_STEUER_ELECTRIC_CENTS = 0
TUV_RESERVE_CENTS = 800                  # ~8 €
MAINTENANCE_CENTS = 5000                 # ~50 €

# Feasibility thresholds on (monthly cost / available budget).
_GOOD_RATIO = 0.75
_TIGHT_RATIO = 1.0

FEASIBILITY_LABELS = {
    "gut": "Gut machbar",
    "knapp": "Knapp",
    "riskant": "Riskant",
}


@dataclass
class AutoExtras:
    vollkasko: bool = True
    is_electric: bool = False
    kfz_steuer: bool = True
    tuv_reserve: bool = True
    maintenance: bool = True


@dataclass
class AutoResult:
    mode: str                              # "standard" | "balloon"
    principal_cents: int
    monthly_financing_cents: int
    extras_breakdown: dict[str, int] = field(default_factory=dict)
    extras_total_cents: int = 0
    monthly_total_cents: int = 0           # financing + extras
    available_budget_cents: int = 0
    remaining_after_auto_cents: int = 0
    feasibility: str = "gut"
    feasibility_label: str = "Gut machbar"
    # Underlying financing detail for the schedule/summary panels.
    annuity_result: object | None = None
    balloon_result: object | None = None


def _extras(price_cents: int, extras: AutoExtras) -> dict[str, int]:
    """Default running-cost amounts from the rules of thumb (no balloon line)."""
    out: dict[str, int] = {}
    if extras.vollkasko:
        out["Vollkasko (0,4 %/Mon.)"] = round_half_up(price_cents * VOLLKASKO_MONTHLY_RATE)
    if extras.kfz_steuer:
        out["Kfz-Steuer"] = (
            KFZ_STEUER_ELECTRIC_CENTS if extras.is_electric else KFZ_STEUER_COMBUSTION_CENTS
        )
    if extras.tuv_reserve:
        out["TÜV-Rücklage"] = TUV_RESERVE_CENTS
    if extras.maintenance:
        out["Wartung & Reifen"] = MAINTENANCE_CENTS
    return out


def _feasibility(monthly_total_cents: int, available_cents: int) -> str:
    if available_cents <= 0:
        return "riskant" if monthly_total_cents > 0 else "gut"
    ratio = monthly_total_cents / available_cents
    if monthly_total_cents > available_cents:
        return "riskant"
    if ratio <= _GOOD_RATIO:
        return "gut"
    if ratio <= _TIGHT_RATIO:
        return "knapp"
    return "riskant"


def compute(
    *,
    price_cents: int,
    down_payment_cents: int = 0,
    annual_rate_pct: float = 0.0,
    term_months: int,
    mode: str = "standard",
    balloon_cents: int = 0,
    extras: AutoExtras | None = None,
    extras_override: dict[str, int] | None = None,
    monthly_disposable_cents: int = 0,
    current_auto_fixed_cents: int = 0,
) -> AutoResult:
    """Compute financing, running costs and household-budget feasibility.

    Running costs come either from ``extras_override`` (explicit, user-edited
    {label: cents} amounts — non-positive entries are dropped) or, if that is
    ``None``, from the boolean ``extras`` rules of thumb. The balloon reserve
    line is always derived from the financing and added on top.
    """
    principal = max(0, price_cents - down_payment_cents)

    annuity_result = None
    balloon_result = None
    balloon_reserve = 0

    if mode == "balloon":
        balloon_result = balloon.compute(principal, balloon_cents, annual_rate_pct, term_months)
        monthly_financing = balloon_result.monthly_payment_cents
        balloon_reserve = balloon_result.recommended_reserve_cents
    else:
        annuity_result = annuity.compute(principal, annual_rate_pct, term_months)
        monthly_financing = annuity_result.monthly_payment_cents

    if extras_override is not None:
        extras_breakdown = {k: int(v) for k, v in extras_override.items() if v and int(v) > 0}
    else:
        extras_breakdown = _extras(price_cents, extras or AutoExtras())
    if balloon_reserve > 0:
        extras_breakdown["Schlussraten-Rücklage"] = balloon_reserve
    extras_total = sum(extras_breakdown.values())
    monthly_total = monthly_financing + extras_total

    # Money currently spent on the car frees up if it is replaced.
    available = monthly_disposable_cents + current_auto_fixed_cents
    remaining = available - monthly_total
    feasibility = _feasibility(monthly_total, available)

    return AutoResult(
        mode=mode,
        principal_cents=principal,
        monthly_financing_cents=monthly_financing,
        extras_breakdown=extras_breakdown,
        extras_total_cents=extras_total,
        monthly_total_cents=monthly_total,
        available_budget_cents=available,
        remaining_after_auto_cents=remaining,
        feasibility=feasibility,
        feasibility_label=FEASIBILITY_LABELS[feasibility],
        annuity_result=annuity_result,
        balloon_result=balloon_result,
    )

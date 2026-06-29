"""Mortgage calculator (German Annuitätendarlehen).

Inputs: purchase price, equity, nominal interest (Sollzins), fixed-rate period
(Sollzinsbindung) and total term (Laufzeit). The loan is the price minus
equity; the instalment fully amortises that loan over the term. We report the
residual debt at the end of the fixed-rate period (Restschuld nach Zinsbindung)
and the interest split, which are the figures a borrower needs for the
follow-up financing decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.calculator import annuity
from modules.calculator.annuity import ScheduleRow


@dataclass
class HouseResult:
    price_cents: int
    equity_cents: int
    loan_cents: int
    annual_rate_pct: float
    fixed_period_years: float
    term_years: float
    monthly_payment_cents: int
    total_interest_cents: int
    total_paid_cents: int
    residual_after_fixed_cents: int
    interest_during_fixed_cents: int
    principal_during_fixed_cents: int
    schedule: list[ScheduleRow] = field(default_factory=list)


def compute(
    *,
    price_cents: int,
    equity_cents: int,
    annual_rate_pct: float,
    fixed_period_years: float,
    term_years: float,
) -> HouseResult:
    if term_years <= 0:
        raise ValueError("Laufzeit muss größer als 0 sein.")
    if equity_cents > price_cents:
        raise ValueError("Eigenkapital darf den Kaufpreis nicht übersteigen.")

    loan = max(0, price_cents - equity_cents)
    term_months = round(term_years * 12)
    result = annuity.compute(loan, annual_rate_pct, term_months)

    fixed_months = min(round(fixed_period_years * 12), len(result.schedule))
    if fixed_months > 0 and fixed_months <= len(result.schedule):
        residual = result.schedule[fixed_months - 1].balance_cents
        interest_fixed = sum(r.interest_cents for r in result.schedule[:fixed_months])
        principal_fixed = sum(r.principal_cents for r in result.schedule[:fixed_months])
    else:
        residual = 0
        interest_fixed = result.total_interest_cents
        principal_fixed = loan

    return HouseResult(
        price_cents=price_cents,
        equity_cents=equity_cents,
        loan_cents=loan,
        annual_rate_pct=annual_rate_pct,
        fixed_period_years=fixed_period_years,
        term_years=term_years,
        monthly_payment_cents=result.monthly_payment_cents,
        total_interest_cents=result.total_interest_cents,
        total_paid_cents=result.total_paid_cents,
        residual_after_fixed_cents=residual,
        interest_during_fixed_cents=interest_fixed,
        principal_during_fixed_cents=principal_fixed,
        schedule=result.schedule,
    )

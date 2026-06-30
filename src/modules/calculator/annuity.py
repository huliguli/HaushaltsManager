"""Annuity-loan maths: payment, full amortisation schedule, reverse solves.

Convention: the quoted interest rate is a *nominal annual rate compounded
monthly*, so the monthly rate is ``i = rate/100/12``. This matches the typical
German "Annuitätenrechner" result. All amounts are integer cents; floats are
used only for the interest factor and rounded straight back to whole cents.

The schedule is built so the final instalment exactly clears the balance:
because the monthly payment is rounded to whole cents, the last row absorbs
the few-cent rounding remainder instead of leaving a stray balance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from modules.money import round_half_up


@dataclass
class ScheduleRow:
    month: int
    payment_cents: int
    interest_cents: int
    principal_cents: int
    balance_cents: int


@dataclass
class AnnuityResult:
    principal_cents: int
    monthly_payment_cents: int
    term_months: int
    annual_rate_pct: float
    total_paid_cents: int
    total_interest_cents: int
    schedule: list[ScheduleRow] = field(default_factory=list)


def monthly_rate(annual_rate_pct: float) -> float:
    return annual_rate_pct / 100.0 / 12.0


def monthly_payment(principal_cents: int, annual_rate_pct: float, term_months: int) -> int:
    """Annuity instalment in cents for a loan paid off over ``term_months``."""
    if term_months <= 0:
        raise ValueError("Laufzeit muss größer als 0 sein.")
    if principal_cents <= 0:
        return 0
    i = monthly_rate(annual_rate_pct)
    if abs(i) < 1e-12:
        pay = principal_cents / term_months
    else:
        pay = principal_cents * i / (1.0 - (1.0 + i) ** (-term_months))
    return round_half_up(pay)


def build_schedule(
    principal_cents: int, annual_rate_pct: float, term_months: int,
    payment_cents: int | None = None,
) -> list[ScheduleRow]:
    """Full month-by-month amortisation table ending at a zero balance."""
    if term_months <= 0:
        raise ValueError("Laufzeit muss größer als 0 sein.")
    # Nothing to amortise: return an empty schedule so compute() reports a term
    # of 0 instead of a phantom all-zero first row (e.g. house price == equity).
    if principal_cents <= 0:
        return []
    pay = payment_cents if payment_cents is not None else monthly_payment(
        principal_cents, annual_rate_pct, term_months
    )
    i = monthly_rate(annual_rate_pct)
    balance = principal_cents
    rows: list[ScheduleRow] = []

    for month in range(1, term_months + 1):
        interest = round_half_up(balance * i)
        is_last = month == term_months
        if is_last:
            principal_part = balance
            this_pay = principal_part + interest
        else:
            this_pay = pay
            principal_part = this_pay - interest
            if principal_part >= balance:  # rounding pushed us to payoff early
                principal_part = balance
                this_pay = principal_part + interest
        balance -= principal_part
        rows.append(ScheduleRow(month, this_pay, interest, principal_part, balance))
        if balance <= 0:
            break
    return rows


def compute(principal_cents: int, annual_rate_pct: float, term_months: int) -> AnnuityResult:
    """Forward calculation: principal + rate + term -> payment + schedule."""
    pay = monthly_payment(principal_cents, annual_rate_pct, term_months)
    schedule = build_schedule(principal_cents, annual_rate_pct, term_months, pay)
    total_paid = sum(r.payment_cents for r in schedule)
    total_interest = sum(r.interest_cents for r in schedule)
    return AnnuityResult(
        principal_cents=principal_cents,
        monthly_payment_cents=pay,
        term_months=len(schedule),
        annual_rate_pct=annual_rate_pct,
        total_paid_cents=total_paid,
        total_interest_cents=total_interest,
        schedule=schedule,
    )


def solve_term_months(principal_cents: int, payment_cents: int, annual_rate_pct: float) -> int:
    """How many months a given instalment needs to clear the loan.

    Raises if the instalment does not even cover the first month's interest
    (the balance would never shrink).
    """
    if payment_cents <= 0:
        raise ValueError("Monatsrate muss größer als 0 sein.")
    if principal_cents <= 0:
        return 0
    i = monthly_rate(annual_rate_pct)
    if abs(i) < 1e-12:
        return math.ceil(principal_cents / payment_cents)
    first_interest = principal_cents * i
    if payment_cents <= first_interest:
        raise ValueError(
            "Die Monatsrate ist zu niedrig – sie deckt nicht einmal die Zinsen, "
            "der Kredit würde nie getilgt."
        )
    n = -math.log(1.0 - principal_cents * i / payment_cents) / math.log(1.0 + i)
    return max(1, math.ceil(n))


def solve_principal(payment_cents: int, annual_rate_pct: float, term_months: int) -> int:
    """Loan amount that a given instalment supports over a term."""
    if term_months <= 0:
        raise ValueError("Laufzeit muss größer als 0 sein.")
    i = monthly_rate(annual_rate_pct)
    if abs(i) < 1e-12:
        return payment_cents * term_months
    return round_half_up(payment_cents * (1.0 - (1.0 + i) ** (-term_months)) / i)

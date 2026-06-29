"""Balloon-loan maths and a direct standard-vs-balloon comparison.

A balloon loan finances ``principal`` with ``n`` monthly instalments plus a
large final payment (the balloon / Schlussrate ``B``). Present-value identity::

    principal = payment * a(n,i) + B * (1+i)^-n      with a(n,i) = (1-(1+i)^-n)/i

so the instalment is::

    payment = (principal - B*(1+i)^-n) * i / (1-(1+i)^-n)

The schedule ends at a balance of exactly ``B`` instead of zero. We also report
the recommended monthly reserve (``B / n``) the borrower should set aside to
actually be able to pay the balloon when it falls due.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.calculator import annuity
from modules.calculator.annuity import AnnuityResult, ScheduleRow, monthly_rate


@dataclass
class BalloonResult:
    principal_cents: int
    balloon_cents: int
    monthly_payment_cents: int
    term_months: int
    annual_rate_pct: float
    total_paid_cents: int            # sum of instalments + balloon
    total_interest_cents: int        # total_paid - principal
    recommended_reserve_cents: int   # balloon / term, to save for the balloon
    effective_monthly_cents: int     # instalment + recommended reserve
    schedule: list[ScheduleRow] = field(default_factory=list)


@dataclass
class BalloonComparison:
    standard: AnnuityResult
    balloon: BalloonResult
    monthly_saving_cents: int        # how much lower the balloon instalment is
    extra_interest_cents: int        # additional interest paid for that comfort
    total_standard_cents: int
    total_balloon_cents: int


def balloon_payment(
    principal_cents: int, balloon_cents: int, annual_rate_pct: float, term_months: int
) -> int:
    """Monthly instalment of a balloon loan, in cents."""
    if term_months <= 0:
        raise ValueError("Laufzeit muss größer als 0 sein.")
    if balloon_cents < 0:
        raise ValueError("Schlussrate darf nicht negativ sein.")
    if balloon_cents > principal_cents:
        raise ValueError("Schlussrate darf den Finanzierungsbetrag nicht übersteigen.")
    i = monthly_rate(annual_rate_pct)
    if abs(i) < 1e-12:
        return round((principal_cents - balloon_cents) / term_months)
    factor = (1.0 + i) ** (-term_months)
    return round((principal_cents - balloon_cents * factor) * i / (1.0 - factor))


def build_schedule(
    principal_cents: int, balloon_cents: int, annual_rate_pct: float,
    term_months: int, payment_cents: int | None = None,
) -> list[ScheduleRow]:
    """Amortisation table that ends with the balance equal to the balloon."""
    # Same guards as balloon_payment, so a direct caller (with an explicit
    # payment_cents) cannot build an impossible schedule.
    if term_months <= 0:
        raise ValueError("Laufzeit muss größer als 0 sein.")
    if balloon_cents < 0:
        raise ValueError("Schlussrate darf nicht negativ sein.")
    if balloon_cents > principal_cents:
        raise ValueError("Schlussrate darf den Finanzierungsbetrag nicht übersteigen.")

    pay = payment_cents if payment_cents is not None else balloon_payment(
        principal_cents, balloon_cents, annual_rate_pct, term_months
    )
    i = monthly_rate(annual_rate_pct)
    balance = principal_cents
    rows: list[ScheduleRow] = []
    for month in range(1, term_months + 1):
        interest = round(balance * i)
        if month == term_months:
            principal_part = balance - balloon_cents
        else:
            principal_part = pay - interest
            # Never amortise below the balloon: this keeps the few-cent rounding
            # drift in the final row (like the annuity schedule) instead of
            # producing a negative final principal / a payment below its interest.
            principal_part = min(principal_part, balance - balloon_cents)
        this_pay = principal_part + interest
        balance -= principal_part
        rows.append(ScheduleRow(month, this_pay, interest, principal_part, balance))
    return rows


def compute(
    principal_cents: int, balloon_cents: int, annual_rate_pct: float, term_months: int
) -> BalloonResult:
    pay = balloon_payment(principal_cents, balloon_cents, annual_rate_pct, term_months)
    schedule = build_schedule(principal_cents, balloon_cents, annual_rate_pct, term_months, pay)
    instalments_total = sum(r.payment_cents for r in schedule)
    total_paid = instalments_total + balloon_cents
    reserve = round(balloon_cents / term_months)
    return BalloonResult(
        principal_cents=principal_cents,
        balloon_cents=balloon_cents,
        monthly_payment_cents=pay,
        term_months=term_months,
        annual_rate_pct=annual_rate_pct,
        total_paid_cents=total_paid,
        total_interest_cents=total_paid - principal_cents,
        recommended_reserve_cents=reserve,
        effective_monthly_cents=pay + reserve,
        schedule=schedule,
    )


def compare(
    principal_cents: int, balloon_cents: int, annual_rate_pct: float, term_months: int
) -> BalloonComparison:
    """Standard annuity vs. balloon over the same principal/rate/term."""
    std = annuity.compute(principal_cents, annual_rate_pct, term_months)
    bal = compute(principal_cents, balloon_cents, annual_rate_pct, term_months)
    return BalloonComparison(
        standard=std,
        balloon=bal,
        monthly_saving_cents=std.monthly_payment_cents - bal.monthly_payment_cents,
        extra_interest_cents=bal.total_interest_cents - std.total_interest_cents,
        total_standard_cents=std.total_paid_cents,
        total_balloon_cents=bal.total_paid_cents,
    )

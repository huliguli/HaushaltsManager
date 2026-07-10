"""Repayment progress of a credit (Qt-free).

Derives "wie viel ist schon getilgt, was ist noch offen" from the credit's
master data alone — no payment bookings exist in the app, so the progress is
the scheduled state: rates due since the start date count as paid. With an
interest rate the remaining debt follows the annuity balance (early rates are
mostly interest); without one it falls back to the linear schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from modules import dates
from modules.money import round_half_up


@dataclass(frozen=True)
class CreditProgress:
    months_total: int
    months_elapsed: int            # rates due so far (schedule, clamped)
    principal_cents: int
    paid_cents: int                # principal repaid so far
    remaining_cents: int           # outstanding principal
    ratio: float                   # paid share, 0.0 .. 1.0
    finished: bool


def _months_total(credit) -> int | None:
    if credit.term_months:
        return int(credit.term_months)
    if credit.start_date and credit.end_date:
        s, e = dates.parse_date(credit.start_date), dates.parse_date(credit.end_date)
        if s and e and e > s:
            return (e.year - s.year) * 12 + (e.month - s.month) + 1
    if credit.total_cents and credit.monthly_cents:
        return -(-int(credit.total_cents) // int(credit.monthly_cents))  # ceil
    return None


def compute(credit, today: date | None = None) -> CreditProgress | None:
    """Progress of a credit, or None when the master data is too thin
    (progress needs a start date, a positive rate and a derivable term)."""
    today = today or date.today()
    monthly = int(credit.monthly_cents or 0)
    start = dates.parse_date(credit.start_date) if credit.start_date else None
    total_months = _months_total(credit)
    if start is None or monthly <= 0 or not total_months or total_months <= 0:
        return None

    # Rates due so far: the first rate is due in the start month.
    elapsed = (today.year - start.year) * 12 + (today.month - start.month) + 1
    elapsed = max(0, min(elapsed, total_months))

    principal = int(credit.total_cents or monthly * total_months)
    rate_pct = float(credit.interest_rate or 0.0)
    if rate_pct > 0:
        # Annuity balance after k rates: B_k = P*(1+i)^k - A*((1+i)^k - 1)/i.
        # Early rates are mostly interest, so linear progress would overstate.
        i = rate_pct / 100.0 / 12.0
        factor = (1.0 + i) ** elapsed
        balance = principal * factor - monthly * (factor - 1.0) / i
        remaining = max(0, round_half_up(balance))
    else:
        remaining = max(0, principal - monthly * elapsed)
    remaining = min(remaining, principal)

    paid = principal - remaining
    finished = elapsed >= total_months or remaining <= 0
    if finished:
        paid, remaining = principal, 0
    ratio = paid / principal if principal else 0.0
    return CreditProgress(
        months_total=total_months, months_elapsed=elapsed,
        principal_cents=principal, paid_cents=paid, remaining_cents=remaining,
        ratio=max(0.0, min(1.0, ratio)), finished=finished)

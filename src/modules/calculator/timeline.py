"""Fixed-cost reduction timeline ("Fixkosten-Abbau").

Given the income and the list of active fixed costs, this builds the
chronological sequence of drop-off events: each future end date removes one or
more costs, lowering the fixed total and raising the amount available after
fixed costs. This is what the dashboard timeline visualises — the user sees
exactly when their monthly burden shrinks and by how much.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from modules import dates
from modules.models import FixedCost


@dataclass
class TimelineEvent:
    date: date
    label: str                         # e.g. "Dez. 2026"
    dropped: list[FixedCost] = field(default_factory=list)
    dropped_amount_cents: int = 0
    new_fixed_total_cents: int = 0
    available_after_fixed_cents: int = 0


@dataclass
class TimelineResult:
    income_cents: int
    current_fixed_total_cents: int
    current_available_cents: int
    events: list[TimelineEvent] = field(default_factory=list)


_MONTHS_DE = [
    "Jan.", "Feb.", "März", "Apr.", "Mai", "Juni",
    "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez.",
]


def _month_label(d: date) -> str:
    return f"{_MONTHS_DE[d.month - 1]} {d.year}"


def build(
    income_cents: int, fixed_costs: list[FixedCost], frm: date | None = None
) -> TimelineResult:
    """Compute the drop-off timeline from today (or ``frm``) onwards."""
    frm = frm or dates.today()

    # Costs currently in effect: started (or no start) and not yet ended.
    current: list[FixedCost] = []
    for c in fixed_costs:
        if not c.active:
            continue
        start = dates.parse_date(c.start_date)
        end = dates.parse_date(c.end_date)
        if start and start > frm:
            continue  # not started yet
        if end and end < frm:
            continue  # already ended
        current.append(c)

    current_total = sum(c.amount_cents for c in current)

    # Group future end dates by calendar month, in chronological order.
    enders: list[tuple[date, FixedCost]] = []
    for c in current:
        end = dates.parse_date(c.end_date)
        if end and end >= frm:
            enders.append((end, c))
    enders.sort(key=lambda t: t[0])

    events: list[TimelineEvent] = []
    running_total = current_total
    grouped: dict[tuple[int, int], list[tuple[date, FixedCost]]] = {}
    for end, c in enders:
        grouped.setdefault((end.year, end.month), []).append((end, c))

    for (_year, _month) in sorted(grouped.keys()):
        bucket = grouped[(_year, _month)]
        end_date = max(t[0] for t in bucket)
        dropped = [t[1] for t in bucket]
        dropped_amount = sum(c.amount_cents for c in dropped)
        running_total -= dropped_amount
        events.append(
            TimelineEvent(
                date=end_date,
                label=_month_label(end_date),
                dropped=dropped,
                dropped_amount_cents=dropped_amount,
                new_fixed_total_cents=running_total,
                available_after_fixed_cents=income_cents - running_total,
            )
        )

    return TimelineResult(
        income_cents=income_cents,
        current_fixed_total_cents=current_total,
        current_available_cents=income_cents - current_total,
        events=events,
    )

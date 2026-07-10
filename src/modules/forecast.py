"""Forward projection of the monthly balance (Qt-free).

The forward mirror of :mod:`history`: instead of recomputing past months it
walks FORWARD from the current month and answers the app's core question —
"wann fällt welcher Posten weg, und wie viel bleibt dann monatlich übrig?".

Every future month combines
  * recurring income only (``income_sources.total_active``) — one-off credits
    must never be projected into the future,
  * fixed costs exactly per month via ``active_for_month`` — start/end dates
    make credit, savings-plan and other drop-offs land in the right month,
  * recurring variable expenses exactly per cadence (monthly/quarterly/yearly
    incl. their end dates, see v2.7.0),
  * plus the average ONE-OFF variable spend of recent completed months as an
    estimate for groceries & Co.

All amounts are integer cents. Nothing here writes to the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from modules import dates
from modules.history import MONTHS_DE_SHORT

# How many completed months feed the one-off spending estimate.
ONEOFF_HISTORY_MONTHS = 6


@dataclass
class ForecastPoint:
    """One projected future month."""

    year: int
    month: int
    income_cents: int = 0
    fixed_cents: int = 0
    variable_cents: int = 0        # recurring occurrences + one-off estimate
    remaining_cents: int = 0       # income - fixed - variable
    cumulative_cents: int = 0      # running sum of remaining since today
    events: list = field(default_factory=list)  # e.g. ["Autokredit fällt weg"]

    @property
    def label(self) -> str:
        return f"{MONTHS_DE_SHORT[self.month - 1]} {self.year}"

    @property
    def short_label(self) -> str:
        return MONTHS_DE_SHORT[self.month - 1]


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    import calendar
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def average_oneoff_cents(expense_repo, ref: date,
                         months: int = ONEOFF_HISTORY_MONTHS) -> int:
    """Average one-off (non-recurring) spend of the last completed months.

    The current month is excluded — it is still filling up and would drag the
    average down. With no history at all the estimate is simply 0.
    """
    y, m = dates.shift_month(ref.year, ref.month, -1)
    total = 0
    for _ in range(max(1, months)):
        start, end = _month_bounds(y, m)
        total += expense_repo.total_for_range(start, end)
        y, m = dates.shift_month(y, m, -1)
    return total // max(1, months)


def project(income_repo, fixed_repo, expense_repo,
            months: int = 12, ref: date | None = None) -> list[ForecastPoint]:
    """Project the next ``months`` months (starting AFTER the current one).

    Events name what changes a month's fixed costs versus the month before:
    drop-offs ("… fällt weg") and scheduled starts ("… beginnt", e.g. a
    savings plan planned for a later month).
    """
    ref = ref or date.today()
    income = income_repo.total_active()
    oneoff_avg = average_oneoff_cents(expense_repo, ref)

    # Baseline for event detection: what is active in the CURRENT month.
    prev_names = {c.name for c in fixed_repo.active_for_month(*_month_bounds(ref.year, ref.month))}

    points: list[ForecastPoint] = []
    cumulative = 0
    y, m = ref.year, ref.month
    for _ in range(max(1, months)):
        y, m = dates.shift_month(y, m, 1)
        start, end = _month_bounds(y, m)
        active = fixed_repo.active_for_month(start, end)
        fixed_sum = sum(c.amount_cents for c in active)
        names = {c.name for c in active}
        events = [f"{n} fällt weg" for n in sorted(prev_names - names)]
        events += [f"{n} beginnt" for n in sorted(names - prev_names)]
        prev_names = names

        recurring_var = expense_repo.recurring_total_for_month(y, m)
        variable = recurring_var + oneoff_avg
        remaining = income - fixed_sum - variable
        cumulative += remaining
        points.append(ForecastPoint(
            year=y, month=m, income_cents=income, fixed_cents=fixed_sum,
            variable_cents=variable, remaining_cents=remaining,
            cumulative_cents=cumulative, events=events))
    return points

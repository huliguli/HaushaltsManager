"""Progress of a persisted savings goal (Qt-free).

Mirrors the idea of :mod:`credit_progress`: no bookings exist for a goal, so
the saved amount is the *scheduled* state — the monthly rate counts as saved
for every month since the start month (inclusive), plus the user's manual
correction (``manual_cents``, e.g. an existing start balance or a skipped
month). That keeps the dashboard honest without a separate bookings table.

All amounts are integer cents. Nothing here writes to the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from modules import dates


@dataclass(frozen=True)
class GoalProgress:
    saved_cents: int               # rate x elapsed months + manual correction
    target_cents: int
    remaining_cents: int           # still missing (0 once reached)
    ratio: float                   # saved share, 0.0 .. 1.0
    months_elapsed: int            # months counted so far (schedule, clamped)
    months_to_go: int | None       # at the current rate; None = never (rate 0)
    eta: tuple[int, int] | None    # (year, month) the target is reached
    reached: bool


def compute(goal, today: date | None = None,
            saved_override: int | None = None) -> GoalProgress:
    """Scheduled progress of a goal. Robust against thin data: a goal without
    a parseable start date simply starts counting today.

    ``saved_override`` replaces the schedule estimate with a real balance —
    used when a Topf is linked to the goal (the pot is the source of truth).
    """
    today = today or date.today()
    start = dates.parse_date(goal.start_date) if goal.start_date else None
    if start is None:
        start = today
    monthly = max(0, int(goal.monthly_cents or 0))
    target = max(0, int(goal.target_cents or 0))

    # Months counted so far: the start month itself already counts (the rate
    # is planned for it), a future start counts nothing yet.
    elapsed = (today.year - start.year) * 12 + (today.month - start.month) + 1
    elapsed = max(0, elapsed)

    if saved_override is not None:
        saved = max(0, int(saved_override))
    else:
        saved = max(0, monthly * elapsed + int(goal.manual_cents or 0))
    remaining = max(0, target - saved)
    reached = target > 0 and saved >= target
    ratio = min(1.0, saved / target) if target else 0.0

    if reached:
        months_to_go: int | None = 0
        eta: tuple[int, int] | None = None
    elif monthly <= 0:
        months_to_go, eta = None, None
    else:
        months_to_go = -(-remaining // monthly)  # ceil
        # This month's rate is already counted, so the next one lands next month.
        eta = dates.shift_month(today.year, today.month, months_to_go)
    return GoalProgress(
        saved_cents=saved, target_cents=target, remaining_cents=remaining,
        ratio=ratio, months_elapsed=elapsed, months_to_go=months_to_go,
        eta=eta, reached=reached)


def eta_label(progress: GoalProgress) -> str:
    """Human German label for when the goal will be reached."""
    if progress.reached:
        return "Ziel erreicht"
    if progress.eta is None:
        return "ohne Sparrate offen"
    year, month = progress.eta
    return f"erreicht ≈ {dates.month_name(month)} {year}"

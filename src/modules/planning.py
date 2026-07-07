"""Turn a computed savings plan or loan into real Haushaltsbuch entries (Qt-free).

A **savings plan** becomes a fixed cost (category "Sparen") that runs for its
term, so the monthly rate is planned into the budget and drops off the
fixed-cost timeline when the goal date is reached.

A **loan** becomes a Credit *plus* a linked fixed cost (category "Kredit"): the
credit shows up in the Kredite view, while the linked fixed cost makes the
monthly instalment count in the household budget and the drop-off timeline —
exactly like a hand-entered credit that is wired to a fixed cost.

Both are ordinary persisted rows, so undoing is just deleting them again. That
deletion is done here (not in the UI) so it stays atomic and unit-testable —
undoing a loan removes both the credit and its linked fixed cost.
"""

from __future__ import annotations

import calendar

from modules import dates
from modules.models import Credit, FixedCost

# Category used for a planned savings rate (added to FIXED_CATEGORIES).
SAVINGS_CATEGORY = "Sparen"
# Note stamped on auto-created rows so they are recognisable as planned entries.
PLAN_NOTE = "Automatisch aus der Planung übernommen"


def term_end_iso(start, months: int) -> str:
    """ISO date of the last day of the final month of an ``months``-long term.

    A 24-month plan starting in July 2026 ends on 30 June 2028 (24 months
    inclusive), so the fixed cost is active in exactly those months.
    """
    y, m = dates.shift_month(start.year, start.month, max(1, int(months)) - 1)
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-{last:02d}"


# -- savings ---------------------------------------------------------------
def plan_savings(fixed_repo, monthly_cents: int, months: int, *,
                 name: str | None = None, start=None) -> int:
    """Create the fixed-cost row for a savings plan; return its id."""
    start = start or dates.today()
    label = name or f"Sparplan ({int(months)} Mon.)"
    fc = FixedCost(
        name=label, amount_cents=int(monthly_cents), category=SAVINGS_CATEGORY,
        start_date=dates.to_iso(start), end_date=term_end_iso(start, months),
        note=PLAN_NOTE, active=True)
    return fixed_repo.add(fc)


def unplan_savings(fixed_repo, fixed_id: int) -> None:
    fixed_repo.delete(fixed_id)


# -- loans -----------------------------------------------------------------
def plan_credit(credit_repo, fixed_repo, *, name: str, total_cents: int | None,
                monthly_cents: int, term_months: int, interest_rate: float | None = None,
                category: str = "Divers", start=None) -> tuple[int, int]:
    """Create a Credit + linked fixed cost; return ``(credit_id, fixed_id)``."""
    start = start or dates.today()
    end_iso = term_end_iso(start, term_months)
    # 1) linked fixed cost — makes the instalment count in the monthly budget.
    fc = FixedCost(
        name=name, amount_cents=int(monthly_cents), category="Kredit",
        start_date=dates.to_iso(start), end_date=end_iso, note=PLAN_NOTE, active=True)
    fixed_id = fixed_repo.add(fc)
    # 2) the credit record, wired to that fixed cost.
    cr = Credit(
        name=name,
        total_cents=int(total_cents) if total_cents else None,
        monthly_cents=int(monthly_cents), term_months=int(term_months),
        start_date=dates.to_iso(start), end_date=end_iso,
        interest_rate=interest_rate, category=category, status="aktiv",
        linked_fixed_cost_id=fixed_id, note=PLAN_NOTE)
    credit_id = credit_repo.add(cr)
    return credit_id, fixed_id


def unplan_credit(credit_repo, fixed_repo, credit_id: int) -> None:
    """Delete a planned credit and its linked fixed cost together."""
    cr = credit_repo.get(credit_id)
    if cr is None:
        return
    if cr.linked_fixed_cost_id is not None:
        fixed_repo.delete(cr.linked_fixed_cost_id)
    credit_repo.delete(credit_id)

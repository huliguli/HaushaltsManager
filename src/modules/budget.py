"""Budget aggregation service (Qt-free, reusable by UI and exporters).

Builds the month's :class:`BudgetOverview` from the repositories and exposes
small helpers for month boundaries used across the app.
"""

from __future__ import annotations

import calendar

from modules.models import BudgetOverview


def month_bounds(year: int, month: int) -> tuple[str, str]:
    """ISO (start, end) date strings for a calendar month."""
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def compute_overview(
    income_repo, fixed_repo, expense_repo, year: int, month: int
) -> BudgetOverview:
    """Income, fixed costs effective this month, and variable spending."""
    start, end = month_bounds(year, month)
    income = income_repo.total_active()
    fixed_costs = fixed_repo.active_for_month(start, end)
    fixed_total = sum(c.amount_cents for c in fixed_costs)
    variable = expense_repo.total_for_range(start, end)
    by_cat = expense_repo.by_category_for_range(start, end)
    # Loan instalments are the fixed costs categorised as "Kredit".
    credits_total = sum(c.amount_cents for c in fixed_costs if c.category == "Kredit")
    return BudgetOverview(
        income_cents=income,
        fixed_cents=fixed_total,
        variable_cents=variable,
        credits_cents=credits_total,
        expenses_by_category=by_cat,
    )

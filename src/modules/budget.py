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
    income_repo, fixed_repo, expense_repo, year: int, month: int,
    var_income_repo=None,
) -> BudgetOverview:
    """Income, fixed costs effective this month, and variable spending.

    Income = recurring active sources + this month's one-off income (imported
    bank credits and the like), so a single transfer counts only in its month
    and never inflates the ongoing monthly income.
    """
    start, end = month_bounds(year, month)
    recurring_income = income_repo.total_active()
    income = recurring_income
    if var_income_repo is not None:
        income += var_income_repo.total_for_month(year, month)
    fixed_costs = fixed_repo.active_for_month(start, end)
    fixed_total = sum(c.amount_cents for c in fixed_costs)
    # Month view counts one-off expenses for this month plus every recurring
    # variable expense that has started by now.
    variable = expense_repo.total_for_month(year, month)
    by_cat = expense_repo.by_category_for_month(year, month)
    # Loan instalments are the fixed costs categorised as "Kredit".
    credits_total = sum(c.amount_cents for c in fixed_costs if c.category == "Kredit")
    return BudgetOverview(
        income_cents=income,
        recurring_income_cents=recurring_income,
        fixed_cents=fixed_total,
        variable_cents=variable,
        credits_cents=credits_total,
        expenses_by_category=by_cat,
    )

"""Calendar-year overview with year-over-year comparison (Qt-free).

The yearly sibling of :mod:`history`: builds every month of ONE calendar year
via ``budget.compute_overview`` (so recurring items are materialised exactly
like the dashboard), then aggregates totals, the per-category year sums, the
12-column category matrix and the savings rate. The current year covers only
the months up to today — a half year must not be read as a bad year.

All amounts are integer cents. Nothing here writes to the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from modules import budget
from modules.history import MonthPoint


@dataclass
class YearOverview:
    year: int
    months_covered: int                 # 12 for past years, today's month this year
    points: list[MonthPoint] = field(default_factory=list)
    income_cents: int = 0
    fixed_cents: int = 0
    variable_cents: int = 0
    remaining_cents: int = 0            # income - fixed - variable
    by_category: dict = field(default_factory=dict)   # year total per category, desc

    @property
    def expenses_cents(self) -> int:
        return self.fixed_cents + self.variable_cents

    @property
    def savings_rate(self) -> float | None:
        """Saved share of income (0.0 .. 1.0, negative when overspent).

        ``None`` without any income — a rate of a zero base is meaningless.
        """
        if self.income_cents <= 0:
            return None
        return self.remaining_cents / self.income_cents

    @property
    def has_data(self) -> bool:
        return any(p.income_cents or p.fixed_cents or p.variable_cents
                   for p in self.points)


def months_covered(year: int, today: date | None = None) -> int:
    """How many months of ``year`` are (partly) in the past: 12 for a past
    year, the current month for this year, 0 for a future year."""
    today = today or date.today()
    if year < today.year:
        return 12
    if year == today.year:
        return today.month
    return 0


def build(income_repo, fixed_repo, expense_repo, var_income_repo,
          year: int, today: date | None = None) -> YearOverview:
    """Aggregate one calendar year, oldest month first."""
    covered = months_covered(year, today)
    ov = YearOverview(year=year, months_covered=covered)
    totals: dict[str, int] = {}
    for month in range(1, covered + 1):
        m_ov = budget.compute_overview(
            income_repo, fixed_repo, expense_repo, year, month,
            var_income_repo=var_income_repo)
        pt = MonthPoint(
            year=year, month=month,
            income_cents=m_ov.income_cents, fixed_cents=m_ov.fixed_cents,
            variable_cents=m_ov.variable_cents, remaining_cents=m_ov.after_all_cents,
            by_category=dict(m_ov.all_by_category))
        ov.points.append(pt)
        ov.income_cents += pt.income_cents
        ov.fixed_cents += pt.fixed_cents
        ov.variable_cents += pt.variable_cents
        ov.remaining_cents += pt.remaining_cents
        for cat, cents in pt.by_category.items():
            totals[cat] = totals.get(cat, 0) + cents
    ov.by_category = dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))
    return ov


def category_matrix(ov: YearOverview) -> tuple[list[str], dict[str, list[int]]]:
    """Category × month matrix: ``(categories_desc, per_month)``.

    ``per_month[cat]`` always has 12 entries (months without coverage or
    spending are 0), so table columns line up for every year.
    """
    per_month: dict[str, list[int]] = {cat: [0] * 12 for cat in ov.by_category}
    for pt in ov.points:
        for cat, cents in pt.by_category.items():
            per_month[cat][pt.month - 1] = cents
    return list(ov.by_category.keys()), per_month


def available_years(expense_repo, var_income_repo,
                    today: date | None = None, limit: int = 12) -> list[int]:
    """Years selectable for reports: current year back to the oldest booking
    (expenses or one-off income), newest first, capped at ``limit``."""
    today = today or date.today()
    first = today.year
    for repo in (expense_repo, var_income_repo):
        earliest = repo.min_date()
        if earliest:
            try:
                first = min(first, int(earliest[:4]))
            except ValueError:
                pass
    years = list(range(today.year, first - 1, -1))
    return years[:limit]

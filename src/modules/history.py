"""Monthly history / trend series (Qt-free, reusable by views and exporters).

Turns the dated financial data into a month-by-month series for the trends
view. Every month is built from :func:`budget.compute_overview`, which
materialises recurring expenses correctly (unlike the raw ``monthly_totals``
aggregate, which counts a recurring template only in its start month and would
diverge from the dashboard). Completed months are additionally written to the
``monthly_summary`` cache as a refreshable snapshot; the current, still-changing
month is always computed live and never frozen.

All amounts are integer cents throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from modules import budget
from modules.models import MonthlySummary

# Short German month names for compact chart axes.
MONTHS_DE_SHORT = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


@dataclass
class MonthPoint:
    """One month of the trend series."""

    year: int
    month: int
    income_cents: int = 0
    fixed_cents: int = 0
    variable_cents: int = 0
    remaining_cents: int = 0
    by_category: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{MONTHS_DE_SHORT[self.month - 1]} {self.year}"

    @property
    def short_label(self) -> str:
        """Compact axis tick (month name; the year is shown once, on change)."""
        return MONTHS_DE_SHORT[self.month - 1]


def _iter_months(ref: date, months: int) -> list[tuple[int, int]]:
    """(year, month) for the last ``months`` months ending at ``ref``, oldest first."""
    y, m = ref.year, ref.month
    seq: list[tuple[int, int]] = []
    for _ in range(max(1, months)):
        seq.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(seq))


def monthly_series(
    income_repo, fixed_repo, expense_repo, var_income_repo,
    summary_repo=None, months: int = 12, ref: date | None = None,
) -> list[MonthPoint]:
    """Build the trend series (oldest → newest) and refresh the snapshot cache.

    ``summary_repo`` is optional: when given, every *completed* month is upserted
    into ``monthly_summary`` (a refreshable cache that stays in sync with the
    live figures, so a later edit to a past month is reflected next time). The
    current month is intentionally never persisted — it is still changing.
    """
    ref = ref or date.today()
    points: list[MonthPoint] = []
    for (y, m) in _iter_months(ref, months):
        ov = budget.compute_overview(
            income_repo, fixed_repo, expense_repo, y, m, var_income_repo=var_income_repo)
        pt = MonthPoint(
            year=y, month=m,
            income_cents=ov.income_cents, fixed_cents=ov.fixed_cents,
            variable_cents=ov.variable_cents, remaining_cents=ov.after_all_cents,
            by_category=dict(ov.expenses_by_category))
        points.append(pt)
        if summary_repo is not None and (y, m) != (ref.year, ref.month):
            summary_repo.upsert(MonthlySummary(
                year=y, month=m, income_cents=pt.income_cents, fixed_cents=pt.fixed_cents,
                variable_cents=pt.variable_cents, remaining_cents=pt.remaining_cents))
    return points


def category_series(
    points: list[MonthPoint], top_n: int = 6,
) -> tuple[list[str], dict[str, list[int]]]:
    """Top-N categories across the whole series + per-month values (cents).

    Returns ``(labels, per_month)`` where ``labels`` is the category order
    (biggest first, with a folded ``"Übrige"`` bucket appended when more than
    ``top_n`` categories exist) and ``per_month[label]`` is a list aligned to
    ``points``. Suitable directly for a stacked bar chart.
    """
    totals: dict[str, int] = {}
    for p in points:
        for cat, val in p.by_category.items():
            totals[cat] = totals.get(cat, 0) + val
    ordered = [c for c, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)]
    top = ordered[:top_n]
    top_set = set(top)
    fold_rest = len(ordered) > top_n

    labels = list(top) + (["Übrige"] if fold_rest else [])
    per_month: dict[str, list[int]] = {lab: [] for lab in labels}
    for p in points:
        for cat in top:
            per_month[cat].append(p.by_category.get(cat, 0))
        if fold_rest:
            rest = sum(v for c, v in p.by_category.items() if c not in top_set)
            per_month["Übrige"].append(rest)
    return labels, per_month

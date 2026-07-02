"""German date parsing/formatting and month arithmetic.

Fixed costs carry optional end dates in several shapes the user actually
typed, e.g. ``14.12.2026`` (full date) or ``03.2032`` (month/year only).
Everything is normalised to :class:`datetime.date` and stored as ISO strings
(``YYYY-MM-DD``) in the database; the UI always shows German ``DD.MM.YYYY``.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime

ISO_FMT = "%Y-%m-%d"

# Full German month names — the single source of truth for month labels across
# the UI (dashboard, month navigator, trends). Avoids the several private copies
# that used to drift apart.
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
             "August", "September", "Oktober", "November", "Dezember"]


def month_name(month: int) -> str:
    """German month name for a 1-based month number."""
    return MONTHS_DE[month - 1]


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Add ``delta`` whole months to (year, month), handling the year wrap.

    The single implementation of the wrap-around arithmetic that the month
    navigators and the dashboard/household views all share. Example: shifting
    December 2026 by +1 gives (2027, 1); January 2025 by -1 gives (2024, 12).
    """
    m = month - 1 + delta
    return year + m // 12, m % 12 + 1


def today() -> date:
    return date.today()


def format_date(d: date | str | None) -> str:
    """Render a date as ``DD.MM.YYYY`` (empty string for ``None``)."""
    if d is None:
        return ""
    if isinstance(d, str):
        d = parse_date(d)
        if d is None:
            return ""
    return d.strftime("%d.%m.%Y")


def to_iso(d: date | None) -> str | None:
    return d.strftime(ISO_FMT) if d else None


def parse_date(text: str | date | None) -> date | None:
    """Parse a user/stored date string. Returns ``None`` if blank/unparseable.

    Accepts ``DD.MM.YYYY``, ``D.M.YYYY``, ``MM.YYYY`` (-> last day of month),
    ``YYYY-MM-DD`` and ``DD/MM/YYYY``.
    """
    if text is None or isinstance(text, date):
        return text
    s = str(text).strip()
    if not s:
        return None

    # Month/year only, e.g. "03.2032" or "03/2032" -> last day of that month.
    # Handled here (not via strptime) so both separators resolve consistently to
    # the last day; an end-of-month end date keeps the cost active that month.
    for sep in (".", "/"):
        if s.count(sep) == 1:
            left, right = s.split(sep)
            if left.isdigit() and right.isdigit() and len(right) == 4:
                month, year = int(left), int(right)
                if 1 <= month <= 12:
                    last = calendar.monthrange(year, month)[1]
                    return date(year, month, last)

    for fmt in ("%d.%m.%Y", "%d.%m.%y", ISO_FMT, "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def add_months(d: date, months: int) -> date:
    """Add (or subtract) whole months, clamping the day to the month length."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def months_between(start: date, end: date) -> int:
    """Whole months from ``start`` to ``end`` (negative if end precedes start).

    Counts a partial month as not-yet-elapsed: only completed months count.
    """
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def months_remaining(end: date | str | None, frm: date | None = None) -> int | None:
    """Number of whole months until ``end`` (>= 0). ``None`` = open-ended.

    Returns a negative number when the end date is already in the past
    (used to flag overdue costs).
    """
    if end is None:
        return None
    if isinstance(end, str):
        end = parse_date(end)
        if end is None:
            return None
    frm = frm or today()
    # +1 so that "ends this month" still counts as one remaining month.
    return months_between(frm, end) + (1 if end >= frm else 0)


def format_months_remaining(months: int | None) -> str:
    """Human German label for a remaining-month count."""
    if months is None:
        return "unbegrenzt"
    if months < 0:
        return "überfällig"
    if months == 0:
        return "läuft aus"
    if months == 1:
        return "noch 1 Monat"
    if months >= 24 and months % 12 == 0:
        return f"noch {months // 12} Jahre"
    return f"noch {months} Monate"

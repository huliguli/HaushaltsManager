"""Abo-Radar: find recurring payments hidden in one-off bookings (Qt-free).

Purely local pattern mining over the booked one-off expenses (bank imports and
hand entries): bookings are grouped by their normalised description, and a
group whose dates repeat in a monthly, quarterly or yearly rhythm with stable
amounts is reported as a suspected subscription — with its yearly cost and a
warning when the price went up. No network, no model: the same transparent
string rules as the import categoriser, inspectable and predictable.

Deliberately conservative: an irregular group (supermarket, online shopping)
fails either the rhythm or the amount-stability check and is never suggested.
Recurring *templates* and fixed costs are the app's already-modelled
subscriptions, so their names are excluded up front.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from modules import dates
from modules.bank_import.model import normalize

# A rhythm needs at least this many bookings before it is trusted.
MIN_OCCURRENCES = 3

# (interval_months, min_gap_days, max_gap_days): tolerant windows, because
# bank bookings shift around weekends and month lengths.
_INTERVALS = (
    (1, 24, 38),
    (3, 76, 108),
    (12, 330, 400),
)

# Amounts within a group may spread by at most this factor. Real subscriptions
# are near-constant (a price rise stays well below this); shopping at the same
# merchant varies wildly and is filtered out here.
MAX_AMOUNT_SPREAD = 1.6

# Ignore sub-25-cent wiggles when flagging a price increase.
PRICE_INCREASE_MIN_CENTS = 25

# UI vocabulary (matches VariableExpense.INTERVAL_LABELS).
INTERVAL_LABELS = {1: "monatlich", 3: "quartalsweise", 12: "jährlich"}

# Expense category -> fixed-cost category for "als Fixkosten übernehmen".
# Anything not mapped lands in "Sonstiges".
_FIXED_CATEGORY_MAP = {
    "Telekommunikation": "Kommunikation",
    "Streaming & Abos": "Freizeit",
    "Freizeit & Unterhaltung": "Freizeit",
    "Versicherung": "Versicherung",
    "Auto & Tanken": "Auto",
    "Mobilität & ÖPNV": "Auto",
    "Energie & Nebenkosten": "Wohnen",
    "Wohnen & Miete": "Wohnen",
    "Finanzen & Gebühren": "Sonstiges",
    "Gesundheit & Apotheke": "Persönlich",
    "Bildung": "Persönlich",
}

# Note stamped on fixed costs created from the radar (recognisable + undoable).
RADAR_NOTE = "Aus dem Abo-Radar übernommen"


@dataclass(frozen=True)
class PriceIncrease:
    old_cents: int
    new_cents: int
    since_iso: str                 # first booking at the new price


@dataclass(frozen=True)
class SuspectedSubscription:
    pattern: str                   # normalised group key (ignore/de-dup handle)
    name: str                      # display name (most recent original text)
    category: str                  # most frequent expense category of the group
    interval_months: int           # 1 / 3 / 12
    amount_cents: int              # current price per booking
    occurrences: int
    first_iso: str
    last_iso: str
    price_increase: PriceIncrease | None = None

    @property
    def monthly_cents(self) -> int:
        """The booking amount spread over its interval (for fixed costs)."""
        return round(self.amount_cents / self.interval_months)

    @property
    def yearly_cents(self) -> int:
        return self.amount_cents * (12 // self.interval_months)

    @property
    def interval_label(self) -> str:
        return INTERVAL_LABELS.get(
            self.interval_months, f"alle {self.interval_months} Monate")


def fixed_category_for(expense_category: str) -> str:
    return _FIXED_CATEGORY_MAP.get(expense_category, "Sonstiges")


def known_patterns(fixed_costs, templates) -> set[str]:
    """Patterns already modelled in the app (active fixed costs + recurring
    templates) — the radar must not re-suggest what the user already planned."""
    known = {normalize(fc.name) for fc in fixed_costs if fc.active}
    known |= {normalize(t.description) for t in templates}
    known.discard("")
    return known


def _match_interval(gaps: list[int]) -> int | None:
    """Interval (months) whose day window contains EVERY gap, or None."""
    for interval, lo, hi in _INTERVALS:
        if all(lo <= g <= hi for g in gaps):
            return interval
    return None


def _price_increase(sorted_items) -> PriceIncrease | None:
    """Flag when the newest bookings are pricier than the level before.

    Walks backwards from the newest booking to the start of the current price
    run; the booking right before that run is the old price. Decreases are not
    flagged — cheaper is not a problem worth a warning.
    """
    current = sorted_items[-1].amount_cents
    run_start = len(sorted_items) - 1
    while run_start > 0 and sorted_items[run_start - 1].amount_cents == current:
        run_start -= 1
    if run_start == 0:
        return None  # one price level across the whole history
    old = sorted_items[run_start - 1].amount_cents
    if current - old < PRICE_INCREASE_MIN_CENTS:
        return None
    return PriceIncrease(old_cents=old, new_cents=current,
                         since_iso=sorted_items[run_start].date)


def detect(expenses, *, ignored: set[str] | frozenset = frozenset(),
           known: set[str] | frozenset = frozenset(),
           today: date | None = None) -> list[SuspectedSubscription]:
    """Suspected subscriptions in a list of one-off expenses, priciest first.

    ``ignored`` are user-dismissed patterns, ``known`` the already-modelled
    ones (see :func:`known_patterns`); both are skipped up front.
    """
    today = today or date.today()
    groups: dict[str, list] = {}
    for e in expenses:
        key = normalize(e.description)
        if not key or key in ignored or key in known:
            continue
        groups.setdefault(key, []).append(e)

    found: list[SuspectedSubscription] = []
    for key, items in groups.items():
        if len(items) < MIN_OCCURRENCES:
            continue
        items.sort(key=lambda e: e.date)
        days = [dates.parse_date(e.date) for e in items]
        if any(d is None for d in days):
            continue
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        interval = _match_interval(gaps)
        if interval is None:
            continue
        amounts = [e.amount_cents for e in items]
        low, high = min(amounts), max(amounts)
        if low <= 0 or high > low * MAX_AMOUNT_SPREAD:
            continue
        # Still active? An ended subscription (no booking for well over one
        # interval) is history, not an action item.
        _iv, _lo, hi = next(w for w in _INTERVALS if w[0] == interval)
        if (today - days[-1]).days > hi * 1.5:
            continue
        cats: dict[str, int] = {}
        for e in items:
            cats[e.category] = cats.get(e.category, 0) + 1
        category = max(cats, key=lambda c: cats[c])
        found.append(SuspectedSubscription(
            pattern=key, name=items[-1].description, category=category,
            interval_months=interval, amount_cents=items[-1].amount_cents,
            occurrences=len(items), first_iso=items[0].date,
            last_iso=items[-1].date, price_increase=_price_increase(items)))
    found.sort(key=lambda s: s.yearly_cents, reverse=True)
    return found


# How far back the scan looks. Three years so a yearly subscription can show
# the three occurrences the rhythm check needs.
SCAN_MONTHS = 36


def scan(expense_repo, fixed_repo, ignore_repo,
         today: date | None = None) -> list[SuspectedSubscription]:
    """Convenience wrapper: gather inputs from the repositories and detect."""
    today = today or date.today()
    y, m = dates.shift_month(today.year, today.month, -SCAN_MONTHS)
    start_iso = f"{y:04d}-{m:02d}-01"
    expenses = expense_repo.list_for_range(start_iso, dates.to_iso(today))
    known = known_patterns(
        fixed_repo.list(only_active=True), expense_repo.list_recurring_templates())
    return detect(expenses, ignored=ignore_repo.all(), known=known, today=today)

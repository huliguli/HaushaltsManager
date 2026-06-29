"""Money handling — strictly integer cents, German number formatting.

All monetary amounts in HaushaltsManager are stored and computed as integer
cents (``int``). This is the single most important rule of the code base:
floats accumulate rounding error and must never represent money. Conversions
to/from float happen only at the boundaries (interest maths, chart drawing)
and are immediately rounded back to whole cents.

German conventions:
    * Thousands separator ".", decimal separator ",", e.g. ``1.234,56 €``
    * Parsing accepts German (``1.234,56``) *and* plain/US (``1234.56``) input,
      which is what bank exports and PDF statements mix in practice.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Non-breaking space between number and currency symbol looks tidy but breaks
# naive parsers; we use a normal space and strip both on the way in.
EURO = "€"


def euros_to_cents(value: float | int | str | Decimal) -> int:
    """Convert a euro amount to integer cents using round-half-up.

    Accepts numbers or already-cleaned numeric strings (``"12.5"``). For
    free-form user/German input use :func:`parse_eur` instead.
    """
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    return int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_euros(cents: int) -> float:
    """Convert integer cents to a float euro value (for charts/maths only)."""
    return cents / 100.0


def format_eur(cents: int, *, symbol: bool = True, plus: bool = False) -> str:
    """Format integer cents as a German currency string.

    >>> format_eur(123456)
    '1.234,56 €'
    >>> format_eur(-50000)
    '-500,00 €'
    >>> format_eur(75000, plus=True)
    '+750,00 €'

    Args:
        symbol: append the euro sign.
        plus: show an explicit ``+`` for positive values (handy for deltas).
    """
    # Inputs are integer cents; coerce defensively with the module's half-up
    # convention (not Python's banker's rounding) for any stray fractional value.
    cents = int(Decimal(cents).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign = "-" if cents < 0 else ("+" if plus and cents > 0 else "")
    whole, rest = divmod(abs(cents), 100)
    # f"{n:,}" groups with commas; swap to German dot grouping.
    grouped = f"{whole:,}".replace(",", ".")
    out = f"{sign}{grouped},{rest:02d}"
    if symbol:
        out += f" {EURO}"
    return out


def format_eur_short(cents: int, *, symbol: bool = True) -> str:
    """Compact form without decimals when the amount is whole euros.

    Used in dense chart labels: ``1.234 €`` instead of ``1.234,00 €``.
    """
    if cents % 100 == 0:
        whole = cents // 100
        sign = "-" if whole < 0 else ""
        grouped = f"{abs(whole):,}".replace(",", ".")
        out = f"{sign}{grouped}"
        return out + (f" {EURO}" if symbol else "")
    return format_eur(cents, symbol=symbol)


class MoneyParseError(ValueError):
    """Raised when a string cannot be interpreted as a money amount."""


def parse_eur(text: str | int | float | None) -> int:
    """Parse free-form German/plain money input into integer cents.

    Handles, among others::

        "1.234,56 €" -> 123456     (German)
        "1234,56"    -> 123456     (German, no grouping)
        "1234.56"    -> 123456     (plain / US decimal)
        "1.234"      -> 123400     (German thousands, no decimals)
        "1.234.567"  -> 123456700  (multiple German thousands groups)
        "-58,80"     -> -5880
        "1.500"      -> 150000

    The rule for the ambiguous "single dot" case: a dot followed by exactly
    three digits is treated as a thousands separator (German bias, matching
    the primary audience and typical bank exports); otherwise it is a decimal
    point. Imported values are always shown in an editable preview, so an
    occasional ambiguous case can be corrected by the user.

    Raises:
        MoneyParseError: on empty or non-numeric input.
    """
    if text is None:
        raise MoneyParseError("Kein Betrag angegeben.")
    if isinstance(text, (int, float)):
        return euros_to_cents(text)

    s = str(text).strip()
    # Strip currency symbols and all whitespace (incl. non-breaking space).
    for token in (EURO, "EUR", "eur", " ", " ", " ", "\t"):
        s = s.replace(token, "")
    if not s:
        raise MoneyParseError("Kein Betrag angegeben.")

    negative = s.startswith("-") or s.startswith("(") and s.endswith(")")
    s = s.lstrip("+-").strip("()")

    has_comma = "," in s
    has_dot = "." in s

    if has_comma and has_dot:
        # Whichever separator appears last is the decimal separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # German: dot=grouping
        else:
            s = s.replace(",", "")  # US: comma=grouping, dot=decimal
    elif has_comma:
        s = s.replace(",", ".")  # comma is the decimal separator
    elif has_dot:
        parts = s.split(".")
        if len(parts) > 2:
            s = "".join(parts)  # several dots -> all thousands separators
        elif len(parts[1]) == 3 and parts[0] != "":
            s = parts[0] + parts[1]  # single dot + 3 digits -> thousands
        # else: a normal decimal point, leave as-is.

    try:
        cents = euros_to_cents(Decimal(s))
    except (InvalidOperation, ValueError) as exc:
        raise MoneyParseError(f"„{text}“ ist kein gültiger Betrag.") from exc
    return -cents if negative else cents


def try_parse_eur(text: str | int | float | None) -> int | None:
    """Like :func:`parse_eur` but returns ``None`` instead of raising."""
    try:
        return parse_eur(text)
    except MoneyParseError:
        return None

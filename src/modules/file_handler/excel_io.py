"""Excel import and export (openpyxl).

Export writes a multi-sheet workbook (overview, fixed-cost timeline, expenses,
credits, amortisation plans). Import reads a sheet, auto-detects the column
layout of common German bank exports (DKB, Sparkasse, Commerzbank, N26, ING)
and returns an editable preview.

Security: any text cell that originates from user data is run through
``_safe_text`` to neutralise spreadsheet formula injection (a leading
=, +, - or @ is prefixed with an apostrophe so Excel treats it as text).
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from modules import dates
from modules.calculator import annuity, timeline
from modules.money import cents_to_euros, parse_eur

_MONEY_FMT = '#,##0.00 €'
_HEADER_FILL = PatternFill("solid", fgColor="1B2330")
_HEADER_FONT = Font(color="FFFFFF", bold=True)


def _safe_text(value) -> str:
    """Neutralise CSV/formula injection in a text cell (OWASP guidance).

    Covers the full set of dangerous lead bytes (=, +, -, @, TAB, CR) and looks
    past leading whitespace so " =cmd" cannot slip through. Kept strict so a
    future CSV export inherits the same protection.
    """
    text = "" if value is None else str(value)
    if text.lstrip()[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _euros(cents: int):
    return cents_to_euros(int(cents))


# --- Export ----------------------------------------------------------------
def _write_header(ws, headers: list[str]) -> None:
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="left")


def _autosize(ws, widths: list[int]) -> None:
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def _money_cell(ws, row: int, col: int, cents: int) -> None:
    cell = ws.cell(row=row, column=col, value=_euros(cents))
    cell.number_format = _MONEY_FMT


def export_workbook(
    path: str | Path, *, income, fixed_costs, expenses, credits, overview,
) -> Path:
    """Write the full multi-sheet report to ``path`` and return it."""
    wb = Workbook()

    # --- Übersicht ---
    ws = wb.active
    ws.title = "Übersicht"
    _write_header(ws, ["Position", "Betrag / Monat"])
    rows = [
        ("Einnahmen", overview.income_cents),
        ("Fixkosten", overview.fixed_cents),
        ("davon Kredite", overview.credits_cents),
        ("Variable Ausgaben", overview.variable_cents),
        ("Verfügbar nach Fixkosten", overview.after_fixed_cents),
        ("Verfügbar nach allem", overview.after_all_cents),
    ]
    for r, (label, cents) in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=_safe_text(label))
        _money_cell(ws, r, 2, cents)
    _autosize(ws, [30, 18])

    # --- Fixkosten-Timeline ---
    ws = wb.create_sheet("Fixkosten-Timeline")
    _write_header(ws, ["Datum", "Wegfallende Kosten", "Betrag", "Neue Fixsumme", "Verfügbar danach"])
    result = timeline.build(overview.income_cents, list(fixed_costs))
    r = 2
    ws.cell(row=r, column=1, value="Jetzt")
    ws.cell(row=r, column=2, value="—")
    _money_cell(ws, r, 3, 0)
    _money_cell(ws, r, 4, result.current_fixed_total_cents)
    _money_cell(ws, r, 5, result.current_available_cents)
    for ev in result.events:
        r += 1
        ws.cell(row=r, column=1, value=dates.format_date(ev.date))
        ws.cell(row=r, column=2, value=_safe_text(", ".join(d.name for d in ev.dropped)))
        _money_cell(ws, r, 3, ev.dropped_amount_cents)
        _money_cell(ws, r, 4, ev.new_fixed_total_cents)
        _money_cell(ws, r, 5, ev.available_after_fixed_cents)
    _autosize(ws, [14, 34, 14, 16, 16])

    # --- Ausgaben ---
    ws = wb.create_sheet("Ausgaben")
    _write_header(ws, ["Datum", "Kategorie", "Beschreibung", "Betrag"])
    for r, e in enumerate(expenses, start=2):
        ws.cell(row=r, column=1, value=dates.format_date(e.date))
        ws.cell(row=r, column=2, value=_safe_text(e.category))
        ws.cell(row=r, column=3, value=_safe_text(e.description))
        _money_cell(ws, r, 4, e.amount_cents)
    _autosize(ws, [14, 16, 36, 14])

    # --- Kredite ---
    ws = wb.create_sheet("Kredite")
    _write_header(ws, ["Bezeichnung", "Kategorie", "Gesamtbetrag", "Rate/Monat", "Ende", "Status"])
    for r, cr in enumerate(credits, start=2):
        ws.cell(row=r, column=1, value=_safe_text(cr.name))
        ws.cell(row=r, column=2, value=_safe_text(cr.category))
        _money_cell(ws, r, 3, cr.total_cents or 0)
        _money_cell(ws, r, 4, cr.monthly_cents or 0)
        ws.cell(row=r, column=5, value=dates.format_date(cr.end_date) or "—")
        ws.cell(row=r, column=6, value=_safe_text(cr.status))
    _autosize(ws, [26, 14, 16, 14, 14, 12])

    # --- Tilgungspläne ---
    ws = wb.create_sheet("Tilgungspläne")
    _write_amortisation_plans(ws, credits)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return Path(path)


def _write_amortisation_plans(ws, credits) -> None:
    """Best-effort amortisation tables for credits that have enough figures."""
    row = 1
    any_plan = False
    for cr in credits:
        principal = cr.total_cents
        term = cr.term_months
        if not term and cr.end_date and cr.start_date:
            sd, ed = dates.parse_date(cr.start_date), dates.parse_date(cr.end_date)
            if sd and ed:
                term = max(1, dates.months_between(sd, ed))
        if not principal and cr.monthly_cents and term:
            principal = cr.monthly_cents * term  # 0 %-Annahme
        if not (principal and term):
            continue

        any_plan = True
        rate = cr.interest_rate or 0.0
        title = ws.cell(row=row, column=1, value=_safe_text(f"Tilgungsplan: {cr.name}"))
        title.font = Font(bold=True)
        row += 1
        for col, head in enumerate(["Monat", "Rate", "Tilgung", "Zinsen", "Restschuld"], start=1):
            c = ws.cell(row=row, column=col, value=head)
            c.font = _HEADER_FONT
            c.fill = _HEADER_FILL
        row += 1
        for sr in annuity.build_schedule(principal, rate, term):
            ws.cell(row=row, column=1, value=sr.month)
            _money_cell(ws, row, 2, sr.payment_cents)
            _money_cell(ws, row, 3, sr.principal_cents)
            _money_cell(ws, row, 4, sr.interest_cents)
            _money_cell(ws, row, 5, sr.balance_cents)
            row += 1
        row += 1  # blank spacer between plans
    if not any_plan:
        ws.cell(row=1, column=1, value="Keine Kredite mit ausreichenden Angaben für einen Tilgungsplan.")
    _autosize(ws, [10, 14, 14, 14, 16])


# --- Import ----------------------------------------------------------------
# Header keywords -> logical field. Lower-cased substring match.
_COLUMN_HINTS = {
    "date": ["datum", "buchungstag", "valuta", "wertstellung", "buchung"],
    "amount": ["betrag", "umsatz", "wert", "soll", "haben", "amount"],
    "description": ["verwendungszweck", "beschreibung", "buchungstext", "umsatztext",
                    "vorgang", "name", "empfänger", "beguenstigter", "auftraggeber"],
    "category": ["kategorie", "category"],
}


def guess_mapping(headers: list[str]) -> dict[str, int | None]:
    """Guess which column index holds date/amount/description/category."""
    mapping: dict[str, int | None] = {"date": None, "amount": None,
                                      "description": None, "category": None}
    lowered = [(i, str(h).strip().lower()) for i, h in enumerate(headers)]
    for field, hints in _COLUMN_HINTS.items():
        for i, head in lowered:
            if any(hint in head for hint in hints):
                mapping[field] = i
                break
    return mapping


def read_preview(path: str | Path, max_rows: int = 500) -> tuple[list[str], list[list], dict]:
    """Read the first sheet: return (headers, data_rows, guessed_mapping)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], [], {"date": None, "amount": None, "description": None, "category": None}
    headers = [("" if h is None else str(h)) for h in rows[0]]
    data = [list(r) for r in rows[1: 1 + max_rows]]
    return headers, data, guess_mapping(headers)


def rows_to_expenses(data_rows: list[list], mapping: dict, default_category: str = "Sonstiges"):
    """Convert mapped rows into VariableExpense models, skipping unparseable ones.

    Returns (expenses, skipped_count). Amounts are taken as absolute values so a
    bank export's negative debits import cleanly as expenses.
    """
    from modules.models import VariableExpense  # local import to avoid cycle

    out = []
    skipped = 0
    di, ai = mapping.get("date"), mapping.get("amount")
    desc_i, cat_i = mapping.get("description"), mapping.get("category")
    for row in data_rows:
        try:
            if ai is None or ai >= len(row):
                skipped += 1
                continue
            cents = parse_eur(row[ai])
            if cents == 0:
                skipped += 1
                continue
            d = dates.parse_date(row[di]) if di is not None and di < len(row) else None
            iso = dates.to_iso(d) if d else dates.to_iso(dates.today())
            desc = str(row[desc_i]) if desc_i is not None and desc_i < len(row) and row[desc_i] else ""
            cat = str(row[cat_i]) if cat_i is not None and cat_i < len(row) and row[cat_i] else default_category
            out.append(VariableExpense(
                date=iso, amount_cents=abs(cents), category=cat or default_category,
                description=desc.strip()))
        except Exception:  # noqa: BLE001 - a bad row must not abort the import
            skipped += 1
    return out, skipped

"""End-to-end tests for the Excel/PDF import-export layer."""

from openpyxl import load_workbook

from modules.file_handler import excel_io, pdf_import, pdf_report
from modules.models import BudgetOverview, Credit, FixedCost, VariableExpense


def _sample():
    overview = BudgetOverview(
        income_cents=230_000, fixed_cents=95_000, variable_cents=68_000,
        credits_cents=7_500,
        expenses_by_category={"Lebensmittel": 30_000, "Tanken": 20_000},
    )
    fixed = [
        FixedCost("Miete", 50_000, "Wohnen"),
        FixedCost("Ratenkredit", 7_500, "Kredit", end_date="2026-12-14"),
    ]
    expenses = [
        VariableExpense("2026-06-05", 3_000, "Lebensmittel", "Supermarkt"),
        VariableExpense("2026-06-10", 5_000, "Tanken", "=cmd|calc"),  # injection attempt
    ]
    credits = [Credit("Autokredit", total_cents=1_500_000, monthly_cents=25_000,
                      term_months=60, interest_rate=4.0, category="Auto")]
    return overview, fixed, expenses, credits


def test_excel_export_and_reload(tmp_path):
    overview, fixed, expenses, credits = _sample()
    out = excel_io.export_workbook(
        tmp_path / "report.xlsx", income=[], fixed_costs=fixed,
        expenses=expenses, credits=credits, overview=overview)
    assert out.exists()

    wb = load_workbook(out)
    assert {"Übersicht", "Fixkosten-Timeline", "Ausgaben", "Kredite",
            "Tilgungspläne"} <= set(wb.sheetnames)
    # The formula-injection attempt must be neutralised (no leading '=').
    ausgaben = wb["Ausgaben"]
    texts = [ausgaben.cell(row=r, column=3).value for r in range(2, ausgaben.max_row + 1)]
    assert all(not (t or "").startswith("=") for t in texts)


def test_excel_import_mapping_and_rows(tmp_path):
    overview, fixed, expenses, credits = _sample()
    path = excel_io.export_workbook(
        tmp_path / "r.xlsx", income=[], fixed_costs=fixed,
        expenses=expenses, credits=credits, overview=overview)
    # Re-read the Ausgaben sheet would need that sheet active; instead test the
    # column guesser directly on a typical bank-export header.
    headers = ["Buchungstag", "Verwendungszweck", "Betrag"]
    mapping = excel_io.guess_mapping(headers)
    assert mapping["date"] == 0
    assert mapping["description"] == 1
    assert mapping["amount"] == 2

    rows = [["05.06.2026", "REWE Markt", "-34,90"], ["07.06.2026", "Aral", "-52,10"]]
    items, skipped = excel_io.rows_to_expenses(rows, mapping)
    assert skipped == 0
    assert len(items) == 2
    assert items[0].amount_cents == 3_490  # absolute value of -34,90


def test_rows_to_expenses_skips_and_fallbacks():
    # The import loop's robustness branches (skip empty/garbage/zero/short rows,
    # fall back to today on a bad date, keep positive amounts) were untested.
    mapping = {"date": 0, "amount": 2, "description": 1, "category": None}
    rows = [
        ["05.06.2026", "REWE", "-34,90"],   # ok -> 3490 (abs)
        ["06.06.2026", "leer", ""],          # empty amount -> skip
        ["07.06.2026", "muell", "abc"],      # unparseable -> skip
        ["08.06.2026", "null", "0,00"],      # zero -> skip
        ["09.06.2026", "kurz"],              # too short for amount index -> skip
        ["", "kein Datum", "12,00"],         # bad date -> today fallback, still imported
        ["10.06.2026", "positiv", "55,00"],  # positive amount kept positive
    ]
    items, skipped = excel_io.rows_to_expenses(rows, mapping)
    assert skipped == 4
    assert len(items) == 3
    assert items[0].amount_cents == 3_490
    assert items[-1].amount_cents == 5_500
    assert all(it.date for it in items)  # the bad-date row got a fallback date


def test_read_preview_empty_and_header_only(tmp_path):
    from openpyxl import Workbook

    empty = tmp_path / "empty.xlsx"
    Workbook().save(empty)
    headers, data, mapping = excel_io.read_preview(empty)
    assert headers == [] and data == []
    assert mapping["amount"] is None

    wb = Workbook()
    wb.active.append(["Datum", "Verwendungszweck", "Betrag"])
    header_only = tmp_path / "headeronly.xlsx"
    wb.save(header_only)
    headers, data, mapping = excel_io.read_preview(header_only)
    assert headers == ["Datum", "Verwendungszweck", "Betrag"]
    assert data == []
    assert mapping["amount"] == 2


def test_pdf_report_and_amount_extraction(tmp_path):
    overview, fixed, expenses, credits = _sample()
    out = pdf_report.generate_monthly_report(
        tmp_path / "bericht.pdf", year=2026, month=6, overview=overview,
        fixed_costs=fixed, expenses=expenses, credits=credits)
    assert out.exists()
    head = out.read_bytes()[:5]
    assert head.startswith(b"%PDF")

    # The generated report contains euro amounts; the extractor should find some.
    amounts = pdf_import.extract_amounts(out)
    assert len(amounts) > 0
    assert all("cents" in a for a in amounts)

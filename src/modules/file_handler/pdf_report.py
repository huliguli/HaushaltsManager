"""PDF monthly report (reportlab) with an embedded expense chart.

Qt-free: the chart is drawn with matplotlib's Agg backend straight to a PNG
buffer, so this module can run during tests or headless exports. The report
contains a summary, the fixed-cost timeline preview, expenses and credits.
"""

from __future__ import annotations

import io
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules import dates
from modules.calculator import timeline
from modules.money import format_eur

_MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"]
_NAVY = colors.HexColor("#1b2330")
_ACCENT = colors.HexColor("#2f6bd8")
_LIGHT = colors.HexColor("#eef1f6")


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle("HMTitle", parent=base["Title"], textColor=_NAVY, fontSize=22))
    base.add(ParagraphStyle("HMSection", parent=base["Heading2"], textColor=_NAVY, fontSize=13,
                            spaceBefore=10, spaceAfter=6))
    base.add(ParagraphStyle("HMMuted", parent=base["Normal"], textColor=colors.HexColor("#5d6877")))
    return base


def _donut_png(by_category: dict[str, int]) -> bytes | None:
    """Render an expense donut to PNG bytes, or None if there is no data."""
    if not by_category:
        return None
    fig = Figure(figsize=(4.2, 2.8), dpi=150)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    cycle = ["#2f6bd8", "#1f9d57", "#d98817", "#d6453d", "#8a93a3",
             "#7c5cff", "#15b8c4", "#e6699a"]
    labels = list(by_category.keys())
    values = [v / 100.0 for v in by_category.values()]
    slice_colors = [cycle[i % len(cycle)] for i in range(len(labels))]
    ax.pie(values, labels=labels, colors=slice_colors, startangle=90, counterclock=False,
           autopct=lambda p: f"{p:.0f}%", textprops={"fontsize": 8},
           wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2))
    ax.set(aspect="equal")
    fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    buf.seek(0)
    return buf.getvalue()


def _money_table(rows: list[tuple[str, str]], styles, col_widths=None) -> Table:
    table = Table(rows, colWidths=col_widths or [95 * mm, 60 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), _NAVY),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _LIGHT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dce1e9")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _data_table(header: list[str], rows: list[list[str]], styles, col_widths) -> Table:
    data = [header] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (0, 1), (-1, -1), _NAVY),
    ]
    # Right-align the last (amount) column.
    style.append(("ALIGN", (len(header) - 1, 0), (-1, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def generate_monthly_report(
    path: str | Path, *, year: int, month: int, overview, fixed_costs, expenses, credits,
) -> Path:
    """Build the monthly PDF report and return its path."""
    styles = _styles()
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Monatsbericht {_MONTHS_DE[month - 1]} {year}",
    )
    story = []

    story.append(Paragraph("HaushaltsManager", styles["HMMuted"]))
    story.append(Paragraph(f"Monatsbericht {_MONTHS_DE[month - 1]} {year}", styles["HMTitle"]))
    story.append(Paragraph(f"Erstellt am {dates.format_date(dates.today())}", styles["HMMuted"]))
    story.append(Spacer(1, 10 * mm))

    # Summary
    story.append(Paragraph("Zusammenfassung", styles["HMSection"]))
    summary_rows = [
        ("Einnahmen", format_eur(overview.income_cents)),
        ("Fixkosten", format_eur(overview.fixed_cents)),
        ("davon Kredite", format_eur(overview.credits_cents)),
        ("Variable Ausgaben", format_eur(overview.variable_cents)),
        ("Verfügbar nach Fixkosten", format_eur(overview.after_fixed_cents)),
        ("Verfügbar nach allem", format_eur(overview.after_all_cents)),
    ]
    story.append(_money_table(summary_rows, styles))
    story.append(Spacer(1, 6 * mm))

    # Expense chart
    png = _donut_png(overview.expenses_by_category)
    if png:
        story.append(Paragraph("Ausgaben nach Kategorie", styles["HMSection"]))
        story.append(Image(io.BytesIO(png), width=110 * mm, height=73 * mm))
        story.append(Spacer(1, 4 * mm))

    # Fixed-cost timeline
    result = timeline.build(overview.income_cents, list(fixed_costs))
    if result.events:
        story.append(Paragraph("Fixkosten-Abbau", styles["HMSection"]))
        rows = [[ev.label, ", ".join(d.name for d in ev.dropped),
                 f"-{format_eur(ev.dropped_amount_cents)}",
                 format_eur(ev.available_after_fixed_cents)] for ev in result.events]
        story.append(_data_table(
            ["Datum", "Wegfallende Kosten", "Betrag", "Verfügbar danach"], rows, styles,
            [22 * mm, 78 * mm, 30 * mm, 35 * mm]))
        story.append(Spacer(1, 6 * mm))

    # Expenses list
    if expenses:
        story.append(Paragraph("Ausgaben", styles["HMSection"]))
        rows = [[dates.format_date(e.date), e.category, (e.description or "")[:40],
                 format_eur(e.amount_cents)] for e in expenses[:40]]
        story.append(_data_table(
            ["Datum", "Kategorie", "Beschreibung", "Betrag"], rows, styles,
            [24 * mm, 30 * mm, 76 * mm, 28 * mm]))

    doc.build(story)
    return Path(path)

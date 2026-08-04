"""PDF reports (reportlab): monthly and annual, in the app's visual language.

Qt-free: charts are drawn with matplotlib's Agg backend straight to PNG
buffers, so this module can run during tests or headless exports. Both
reports share one design system — navy header band with the wordmark, KPI
cards with coloured accent bars, sectioned tables with zebra rows, coloured
plus/minus values and a footer with page numbers.
"""

from __future__ import annotations

import io
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app_meta import APP_VERSION
from modules import dates
from modules.calculator import timeline
from modules.money import format_eur, format_eur_short

_MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"]

# The app's palette (ui/theme.py) so reports look like the program itself.
_NAVY = colors.HexColor("#1b2330")
_ACCENT = colors.HexColor("#2f6bd8")
_LIGHT = colors.HexColor("#eef1f6")
_CARD = colors.HexColor("#f6f8fb")
_BORDER = colors.HexColor("#dce1e9")
_MUTED = colors.HexColor("#5d6877")
_GREEN = colors.HexColor("#1f9d57")
_RED = colors.HexColor("#d6453d")
_AMBER = colors.HexColor("#d98817")
_GREY = colors.HexColor("#8a93a3")

_CHART_CYCLE = ["#2f6bd8", "#1f9d57", "#d98817", "#d6453d", "#8a93a3",
                "#7c5cff", "#15b8c4", "#e6699a"]

_PAGE_W = A4[0]
_MARGIN = 16 * mm
_CONTENT_W = _PAGE_W - 2 * _MARGIN


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle("HMBrand", parent=base["Normal"], fontName="Helvetica-Bold",
                            fontSize=9, textColor=colors.HexColor("#9fb6e4")))
    base.add(ParagraphStyle("HMTitle", parent=base["Title"], fontName="Helvetica-Bold",
                            fontSize=21, textColor=colors.white, alignment=0,
                            spaceBefore=0, spaceAfter=0, leading=25))
    base.add(ParagraphStyle("HMHeadDate", parent=base["Normal"], fontSize=8.5,
                            textColor=colors.HexColor("#c6d0e2"), alignment=TA_RIGHT))
    base.add(ParagraphStyle("HMSection", parent=base["Heading2"], fontName="Helvetica-Bold",
                            textColor=_NAVY, fontSize=12.5, spaceBefore=0, spaceAfter=0))
    base.add(ParagraphStyle("HMMuted", parent=base["Normal"], textColor=_MUTED, fontSize=9))
    base.add(ParagraphStyle("HMKpiLabel", parent=base["Normal"], fontSize=8,
                            textColor=_MUTED, leading=10))
    base.add(ParagraphStyle("HMKpiValue", parent=base["Normal"], fontName="Helvetica-Bold",
                            fontSize=14.5, textColor=_NAVY, leading=18))
    base.add(ParagraphStyle("HMKpiHint", parent=base["Normal"], fontSize=7.5,
                            textColor=_GREY, leading=9))
    return base


# --- building blocks ---------------------------------------------------------
def _header_band(styles, title: str, subtitle: str) -> Table:
    """Full-width navy band with the wordmark, report title and date."""
    left = [Paragraph("HAUSHALTSMANAGER", styles["HMBrand"]),
            Paragraph(title, styles["HMTitle"])]
    right = [Paragraph(subtitle.replace("\n", "<br/>"), styles["HMHeadDate"])]
    band = Table([[left, right]], colWidths=[_CONTENT_W * 0.66, _CONTENT_W * 0.34])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (0, -1), 14),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 14),
        # Accent baseline under the band — the report's signature line.
        ("LINEBELOW", (0, -1), (-1, -1), 2.2, _ACCENT),
    ]))
    return band


def _kpi_cards(styles, cards: list) -> Table:
    """Row of stat cards: ``cards`` = [(label, value, accent_color, hint)].

    Rendered like the dashboard's StatCards: soft surface, a coloured accent
    bar on the left edge (LINEBEFORE) and a bold value.
    """
    gap = 4 * mm
    n = len(cards)
    card_w = (_CONTENT_W - gap * (n - 1)) / n
    row = []
    widths = []
    for i, (label, value, color, hint) in enumerate(cards):
        cell = [Paragraph(label, styles["HMKpiLabel"]),
                Paragraph(value, ParagraphStyle(
                    f"kpi{i}", parent=styles["HMKpiValue"], textColor=color))]
        if hint:
            cell.append(Paragraph(hint, styles["HMKpiHint"]))
        row.append(cell)
        widths.append(card_w)
        if i < n - 1:
            row.append("")
            widths.append(gap)
    table = Table([row], colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 8),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    for i, (_label, _value, color, _hint) in enumerate(cards):
        col = i * 2
        style += [
            ("BACKGROUND", (col, 0), (col, -1), _CARD),
            ("BOX", (col, 0), (col, -1), 0.6, _BORDER),
            ("LINEBEFORE", (col, 0), (col, -1), 2.6, color),
            ("LEFTPADDING", (col, 0), (col, -1), 9),
        ]
    table.setStyle(TableStyle(style))
    return table


def _section_flowables(styles, text: str) -> list:
    """Section heading: title with a short accent tick and a hairline rule."""
    return [
        Spacer(1, 7 * mm),
        Paragraph(text, styles["HMSection"]),
        Spacer(1, 1.5),
        HRFlowable(width=14 * mm, thickness=2, color=_ACCENT,
                   spaceAfter=0, hAlign="LEFT"),
        HRFlowable(width="100%", thickness=0.5, color=_BORDER,
                   spaceBefore=-1.2, spaceAfter=5, hAlign="LEFT"),
    ]


def _section(story, styles, text: str) -> None:
    story.extend(_section_flowables(styles, text))


def _chart_section(story, styles, text: str, image: Image) -> None:
    """Heading + chart as one block, so the title never strands at a page end."""
    story.append(KeepTogether(_section_flowables(styles, text) + [image]))


def _money_para(cents: int, styles, *, signed: bool = False, bold: bool = True):
    """Money value as a right-aligned Paragraph, green/red when ``signed``."""
    color = _NAVY
    if signed:
        color = _GREEN if cents >= 0 else _RED
    return Paragraph(format_eur(cents, plus=signed and cents > 0), ParagraphStyle(
        "money", fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=9, textColor=color, alignment=TA_RIGHT))


def _delta_para(cents: int, *, good_up: bool):
    """Year-over-year delta with dashboard semantics: less spending is GREEN.

    ``good_up`` says whether an increase is good (income, balance) or bad
    (fixed/variable costs) — the colour follows the meaning, not the sign.
    """
    if cents == 0:
        return Paragraph("±0,00 €", ParagraphStyle(
            "delta0", fontSize=9, textColor=_GREY, alignment=TA_RIGHT))
    good = (cents > 0) == good_up
    return Paragraph(format_eur(cents, plus=True), ParagraphStyle(
        "delta", fontName="Helvetica-Bold", fontSize=9,
        textColor=_GREEN if good else _RED, alignment=TA_RIGHT))


def _data_table(header: list[str], rows: list[list], col_widths,
                right_cols: tuple[int, ...] | None = None) -> Table:
    """Standard data table: navy header, zebra rows, hairline separators."""
    data = [header] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, _BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 1), (-1, -1), _NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for col in (right_cols if right_cols is not None else (len(header) - 1,)):
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def _footer(footer_text: str):
    """Per-page decorator: hairline + report name left, page number right."""
    def draw(canvas, _doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(_BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(_MARGIN, 12 * mm, _PAGE_W - _MARGIN, 12 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawString(_MARGIN, 8.6 * mm, footer_text)
        canvas.drawRightString(_PAGE_W - _MARGIN, 8.6 * mm,
                               "Seite " + str(canvas.getPageNumber()))
        canvas.restoreState()
    return draw


def _doc(path, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path), pagesize=A4, topMargin=14 * mm, bottomMargin=18 * mm,
        leftMargin=_MARGIN, rightMargin=_MARGIN, title=title)


# --- charts (matplotlib Agg -> PNG bytes) ------------------------------------
def _style_chart_axes(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#dce1e9")
    ax.tick_params(colors="#5d6877", labelsize=8, length=0)
    ax.grid(axis="y", color="#e4e9f1", linewidth=0.8)
    ax.set_axisbelow(True)


def _donut_png(by_category: dict[str, int]) -> bytes | None:
    """Expense donut with the total in the centre and a euro legend."""
    if not by_category:
        return None
    fig = Figure(figsize=(6.2, 3.1), dpi=150)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    items = list(by_category.items())
    labels = [k for k, _ in items]
    values = [v / 100.0 for _, v in items]
    total_cents = sum(v for _, v in items)
    slice_colors = [_CHART_CYCLE[i % len(_CHART_CYCLE)] for i in range(len(labels))]
    wedges, _texts, _autotexts = ax.pie(
        values, colors=slice_colors, startangle=90, counterclock=False,
        autopct=lambda p: f"{p:.0f} %" if p >= 6 else "",  # hide labels on slivers
        pctdistance=0.80,
        textprops={"color": "white", "fontsize": 8, "fontweight": "bold"},
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
    )
    ax.set(aspect="equal")
    ax.text(0, 0, format_eur_short(total_cents), ha="center", va="center",
            fontsize=12, fontweight="bold", color="#1b2330")
    legend_labels = [f"{lab}  ·  {format_eur(by_category[lab])}" for lab in labels]
    ax.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(0.98, 0.5),
              frameon=False, fontsize=8.5)
    fig.subplots_adjust(left=0.00, right=0.60, top=0.97, bottom=0.03)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    buf.seek(0)
    return buf.getvalue()


def _months_bar_png(points) -> bytes | None:
    """Grouped bars (Einnahmen vs. Ausgaben) + balance line for the year report."""
    if not points:
        return None
    fig = Figure(figsize=(7.2, 2.6), dpi=150)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    _style_chart_axes(ax)
    xs = list(range(len(points)))
    income = [p.income_cents / 100.0 for p in points]
    out = [(p.fixed_cents + p.variable_cents) / 100.0 for p in points]
    saldo = [p.remaining_cents / 100.0 for p in points]
    width = 0.38
    ax.bar([x - width / 2 for x in xs], income, width=width, color="#2f6bd8",
           label="Einnahmen", zorder=3)
    ax.bar([x + width / 2 for x in xs], out, width=width, color="#d98817",
           label="Ausgaben", zorder=3)
    ax.plot(xs, saldo, color="#1f9d57", linewidth=2.0, marker="o", markersize=3.5,
            label="Saldo", zorder=4)
    ax.axhline(0, color="#dce1e9", linewidth=1.0)
    ax.set_xticks(xs)
    ax.set_xticklabels([_MONTHS_DE[p.month - 1][:3] for p in points])
    # Legend ABOVE the plot area so it can never overlap the tallest bars.
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), frameon=False,
              fontsize=8, ncol=3, borderaxespad=0)
    fig.subplots_adjust(left=0.075, right=0.99, top=0.86, bottom=0.14)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    buf.seek(0)
    return buf.getvalue()


def _pct(rate: float | None) -> str:
    """German percent label for a savings rate ('–' without income)."""
    if rate is None:
        return "–"
    return f"{rate * 100:.1f} %".replace(".", ",")


# --- annual report ------------------------------------------------------------
def generate_year_report(path: str | Path, *, overview, prev_overview=None) -> Path:
    """Build the annual PDF report (Jahresbericht) and return its path.

    ``overview``/``prev_overview`` are :class:`modules.annual.YearOverview`
    instances; with a non-empty previous year every summary row carries the
    year-over-year delta.
    """
    styles = _styles()
    year = overview.year
    has_prev = prev_overview is not None and prev_overview.has_data
    covered = (f"Januar bis {_MONTHS_DE[overview.months_covered - 1]} {year}"
               if 0 < overview.months_covered < 12 else f"Kalenderjahr {year}")
    doc = _doc(path, f"Jahresbericht {year}")
    story = []

    story.append(_header_band(
        styles, f"Jahresbericht {year}",
        f"{covered}\nerstellt am {dates.format_date(dates.today())}"))
    story.append(Spacer(1, 7 * mm))

    saldo_color = _GREEN if overview.remaining_cents >= 0 else _RED
    rate = overview.savings_rate
    story.append(_kpi_cards(styles, [
        ("EINNAHMEN", format_eur(overview.income_cents), _ACCENT,
         f"{overview.months_covered} Monate"),
        ("AUSGABEN", format_eur(overview.expenses_cents), _AMBER, "Fix + variabel"),
        ("SALDO (GESPART)", format_eur(overview.remaining_cents), saldo_color,
         "Einnahmen − alle Ausgaben"),
        ("SPARQUOTE", _pct(rate),
         _GREEN if (rate or 0) >= 0 else _RED, "Anteil der Einnahmen"),
    ]))

    # Summary, with the previous year and delta when available.
    _section(story, styles, "Jahr im Überblick" + (f" – Vergleich zu {year - 1}" if has_prev else ""))
    # good_up per row: more income/balance is good, more cost is bad — the
    # delta colour follows the meaning (a drop in Fixkosten shows GREEN).
    summary = [
        ("Einnahmen", overview.income_cents,
         prev_overview.income_cents if has_prev else None, True),
        ("Fixkosten", overview.fixed_cents,
         prev_overview.fixed_cents if has_prev else None, False),
        ("Variable Ausgaben", overview.variable_cents,
         prev_overview.variable_cents if has_prev else None, False),
        ("Saldo (gespart)", overview.remaining_cents,
         prev_overview.remaining_cents if has_prev else None, True),
    ]
    if has_prev:
        rows = [[label, format_eur(cur), format_eur(prev),
                 _delta_para(cur - prev, good_up=good_up)]
                for label, cur, prev, good_up in summary]
        rows.append(["Sparquote", _pct(overview.savings_rate),
                     _pct(prev_overview.savings_rate), ""])
        story.append(_data_table(
            ["Position", str(year), str(prev_overview.year), "Δ zum Vorjahr"],
            rows, [_CONTENT_W * 0.37, _CONTENT_W * 0.21, _CONTENT_W * 0.21,
                   _CONTENT_W * 0.21], right_cols=(1, 2, 3)))
        if overview.months_covered < 12:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                f"Hinweis: {year} umfasst erst Januar bis "
                f"{_MONTHS_DE[overview.months_covered - 1]} – der Vergleich zum "
                f"vollständigen Jahr {year - 1} fällt entsprechend kleiner aus.",
                styles["HMMuted"]))
    else:
        rows = [[label, _money_para(cur, styles, signed=(label.startswith("Saldo")))]
                for label, cur, _prev, _good_up in summary]
        rows.append(["Sparquote", Paragraph(_pct(overview.savings_rate), ParagraphStyle(
            "rate", fontName="Helvetica-Bold", fontSize=9, textColor=_NAVY,
            alignment=TA_RIGHT))])
        story.append(_data_table(["Position", str(year)], rows,
                                 [_CONTENT_W * 0.62, _CONTENT_W * 0.38]))

    # Month bars + balance line.
    bars = _months_bar_png(overview.points)
    if bars:
        _chart_section(story, styles, "Monate im Vergleich",
                       Image(io.BytesIO(bars), width=_CONTENT_W,
                             height=_CONTENT_W * 2.6 / 7.2))

    # Year expense donut.
    png = _donut_png(overview.by_category)
    if png:
        _chart_section(story, styles, "Ausgaben nach Kategorie",
                       Image(io.BytesIO(png), width=168 * mm, height=84 * mm))

    # Month-by-month table with coloured balances.
    if overview.points:
        _section(story, styles, "Monatswerte")
        rows = [[_MONTHS_DE[p.month - 1], format_eur(p.income_cents),
                 format_eur(p.fixed_cents + p.variable_cents),
                 _money_para(p.remaining_cents, styles, signed=True)]
                for p in overview.points]
        story.append(_data_table(
            ["Monat", "Einnahmen", "Ausgaben", "Saldo"], rows,
            [_CONTENT_W * 0.28, _CONTENT_W * 0.24, _CONTENT_W * 0.24,
             _CONTENT_W * 0.24], right_cols=(1, 2, 3)))

    # Version stamp: a report must reveal which app version produced it (an
    # old-looking export is then diagnosable at a glance).
    deco = _footer(f"HaushaltsManager {APP_VERSION} · Jahresbericht {year}")
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return Path(path)


# --- monthly report ------------------------------------------------------------
def generate_monthly_report(
    path: str | Path, *, year: int, month: int, overview, fixed_costs, expenses, credits,
) -> Path:
    """Build the monthly PDF report and return its path."""
    styles = _styles()
    month_label = f"{_MONTHS_DE[month - 1]} {year}"
    doc = _doc(path, f"Monatsbericht {month_label}")
    story = []

    story.append(_header_band(
        styles, f"Monatsbericht {month_label}",
        f"erstellt am {dates.format_date(dates.today())}"))
    story.append(Spacer(1, 7 * mm))

    remaining = overview.after_all_cents
    story.append(_kpi_cards(styles, [
        ("EINNAHMEN", format_eur(overview.income_cents), _ACCENT, "Im Monat"),
        ("FIXKOSTEN", format_eur(overview.fixed_cents), _AMBER,
         f"davon Kredite {format_eur(overview.credits_cents)}"),
        ("VARIABLE AUSGABEN", format_eur(overview.variable_cents), _GREY, "Erfasst"),
        ("VERBLEIBEND", format_eur(remaining),
         _GREEN if remaining >= 0 else _RED, "Nach allen Kosten"),
    ]))

    # Availability summary.
    _section(story, styles, "Zusammenfassung")
    rows = [
        ["Einnahmen", format_eur(overview.income_cents)],
        ["Fixkosten", format_eur(overview.fixed_cents)],
        ["davon Kredite", format_eur(overview.credits_cents)],
        ["Variable Ausgaben", format_eur(overview.variable_cents)],
        ["Verfügbar nach Fixkosten",
         _money_para(overview.after_fixed_cents, styles, signed=True)],
        ["Verfügbar nach allem", _money_para(remaining, styles, signed=True)],
    ]
    story.append(_data_table(["Position", "Betrag"], rows,
                             [_CONTENT_W * 0.62, _CONTENT_W * 0.38]))

    # Expense chart.
    png = _donut_png(overview.all_by_category)
    if png:
        _chart_section(story, styles, "Ausgaben nach Kategorie",
                       Image(io.BytesIO(png), width=168 * mm, height=84 * mm))

    # Fixed-cost timeline — recurring income only (one-off credits don't recur).
    result = timeline.build(overview.recurring_income_cents, list(fixed_costs))
    if result.events:
        _section(story, styles, "Fixkosten-Abbau")
        rows = [[ev.label, ", ".join(d.name for d in ev.dropped),
                 f"-{format_eur(ev.dropped_amount_cents)}",
                 format_eur(ev.available_after_fixed_cents)] for ev in result.events]
        story.append(_data_table(
            ["Datum", "Wegfallende Kosten", "Betrag", "Verfügbar danach"], rows,
            [24 * mm, _CONTENT_W - 24 * mm - 30 * mm - 36 * mm, 30 * mm, 36 * mm],
            right_cols=(2, 3)))

    # Expenses list (largest first would reorder the booking view; keep order,
    # cap the table and say so instead of truncating silently).
    if expenses:
        _section(story, styles, "Ausgaben im Monat")
        shown = expenses[:40]
        rows = [[dates.format_date(e.date), e.category, (e.description or "")[:44],
                 format_eur(e.amount_cents)] for e in shown]
        story.append(_data_table(
            ["Datum", "Kategorie", "Beschreibung", "Betrag"], rows,
            [24 * mm, 42 * mm, _CONTENT_W - 24 * mm - 42 * mm - 28 * mm, 28 * mm],
            right_cols=(3,)))
        if len(expenses) > len(shown):
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                f"… und {len(expenses) - len(shown)} weitere Buchungen "
                f"(vollständig im Excel-Monatsüberblick).", styles["HMMuted"]))

    # Version stamp (see year report): which app version produced this file.
    deco = _footer(f"HaushaltsManager {APP_VERSION} · Monatsbericht {month_label}")
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return Path(path)

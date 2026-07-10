"""Verlauf: the month-over-month trends cockpit (v2.0.0 flagship).

Turns the already-recorded data into a story over time: a line chart of income
vs. spending vs. balance, a stacked bar chart of the top spending categories per
month, and a few average KPIs across the selected range. Data comes from the
Qt-free :mod:`modules.history` service (built on compute_overview, so recurring
items are materialised exactly like the dashboard) and the monthly_summary cache
it keeps in sync.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from modules import history
from modules.money import format_eur, format_eur_short
from ui import theme
from ui.views.base_view import BaseView
from ui.widgets.chart_canvas import ChartCanvas
from ui.widgets.common import StatCard, heading, muted

_RANGES = [("6 Monate", 6), ("12 Monate", 12), ("24 Monate", 24)]


class VerlaufView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._months = 12
        c = self.ctx.colors

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._body = QVBoxLayout(container)
        self._body.setContentsMargins(30, 26, 30, 26)
        self._body.setSpacing(18)
        scroll.setWidget(container)

        # Header with the range selector.
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(heading("Verlauf"))
        title_box.addWidget(muted("Wie sich Einnahmen, Ausgaben und Saldo über die Monate entwickeln."))
        header.addLayout(title_box)
        header.addStretch(1)
        header.addWidget(self._range_label("Zeitraum"))
        self._range = QComboBox()
        for label, months in _RANGES:
            self._range.addItem(label, months)
        self._range.setCurrentIndex(1)  # 12 months
        self._range.setAccessibleName("Zeitraum in Monaten")
        self._range.currentIndexChanged.connect(self._on_range_changed)
        header.addWidget(self._range)
        self._body.addLayout(header)

        # KPI row (averages over the range).
        self._kpi_row = QWidget()
        self._kpi_layout = QHBoxLayout(self._kpi_row)
        self._kpi_layout.setContentsMargins(0, 0, 0, 0)
        self._kpi_layout.setSpacing(16)
        self._income_card = StatCard("Ø Einnahmen / Monat", c["blue"])
        self._expense_card = StatCard("Ø Ausgaben / Monat", c["amber"])
        self._saldo_card = StatCard("Ø Saldo / Monat", c["green"])
        self._saved_card = StatCard("Saldo gesamt", c["primary"])
        for card in (self._income_card, self._expense_card, self._saldo_card, self._saved_card):
            self._kpi_layout.addWidget(card, 1)
        self._body.addWidget(self._kpi_row)

        # Line chart card.
        self._line_card, line_body = self._chart_card(
            "Einnahmen, Ausgaben & Saldo")
        self._line_canvas = ChartCanvas(c, width=6.6, height=2.9)
        self._line_canvas.setMinimumHeight(250)
        self._line_canvas.setAccessibleName("Verlauf Einnahmen, Ausgaben und Saldo")
        line_body.addWidget(self._line_canvas)
        self._line_legend = self._legend_row()
        line_body.addWidget(self._line_legend)
        self._body.addWidget(self._line_card)

        # Stacked category bars card.
        self._bar_card, bar_body = self._chart_card("Ausgaben nach Kategorie")
        self._bar_canvas = ChartCanvas(c, width=6.6, height=3.1)
        self._bar_canvas.setMinimumHeight(260)
        self._bar_canvas.setAccessibleName("Ausgaben nach Kategorie über die Monate")
        bar_body.addWidget(self._bar_canvas)
        self._bar_legend = QWidget()
        self._bar_legend_layout = QGridLayout(self._bar_legend)
        self._bar_legend_layout.setContentsMargins(0, 6, 0, 0)
        self._bar_legend_layout.setHorizontalSpacing(16)
        self._bar_legend_layout.setVerticalSpacing(4)
        bar_body.addWidget(self._bar_legend)
        self._body.addWidget(self._bar_card)
        self._body.addStretch(1)

    # -- builders -----------------------------------------------------------
    def _range_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FieldLabel")
        return lbl

    def _chart_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        body = QVBoxLayout(card)
        body.setContentsMargins(22, 20, 22, 18)
        body.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("H2")
        body.addWidget(t)
        return card, body

    def _legend_row(self) -> QWidget:
        wrap = QWidget()
        self._line_legend_layout = QHBoxLayout(wrap)
        self._line_legend_layout.setContentsMargins(0, 4, 0, 0)
        self._line_legend_layout.setSpacing(18)
        return wrap

    def _dot_label(self, text: str, color: str) -> QWidget:
        cell = QWidget()
        row = QHBoxLayout(cell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 13px;")
        lbl = QLabel(text)
        lbl.setObjectName("Faint")
        row.addWidget(dot)
        row.addWidget(lbl)
        row.addStretch(1)
        return cell

    # -- events -------------------------------------------------------------
    def _on_range_changed(self) -> None:
        self._months = self._range.currentData()
        self.refresh()

    def on_theme_changed(self) -> None:
        c = self.ctx.colors
        self._line_canvas.set_colors(c)
        self._bar_canvas.set_colors(c)
        self.refresh()

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        c = self.ctx.colors
        points = history.monthly_series(
            self.ctx.income, self.ctx.fixed, self.ctx.expenses, self.ctx.var_income,
            self.ctx.summaries, months=self._months, ref=date.today())
        labels = [p.short_label for p in points]

        # Empty history: no entry in the whole range. Show a clear pointer to
        # the household book instead of a wall of misleading "0,00 €" KPIs.
        if not any(p.income_cents or p.fixed_cents or p.variable_cents for p in points):
            for card in (self._income_card, self._expense_card,
                         self._saldo_card, self._saved_card):
                card.set_value("–", c["text_faint"])
                card.set_hint("Noch keine Daten")
            self._income_card.set_hint(
                "Erfasse Einnahmen und Ausgaben im Haushaltsbuch")
            self._line_canvas.line_series([], [])
            self._bar_canvas.bars_stacked([], [])
            self._fill_line_legend([])
            self._fill_bar_legend([], theme.chart_colors(c))
            return

        # KPIs (averages across the range).
        n = max(1, len(points))
        avg_income = sum(p.income_cents for p in points) // n
        avg_out = sum(p.fixed_cents + p.variable_cents for p in points) // n
        avg_saldo = sum(p.remaining_cents for p in points) // n
        total_saldo = sum(p.remaining_cents for p in points)
        self._income_card.set_value(format_eur(avg_income), c["text"])
        self._income_card.set_hint(f"über {n} Monate")
        self._expense_card.set_value(format_eur(avg_out), c["text"])
        self._expense_card.set_hint("Fix + variabel")
        self._saldo_card.set_accent(c["green"] if avg_saldo >= 0 else c["red"])
        self._saldo_card.set_value(format_eur(avg_saldo), c["green"] if avg_saldo >= 0 else c["red"])
        self._saldo_card.set_hint("Einnahmen − alle Ausgaben")
        self._saved_card.set_accent(c["primary"] if total_saldo >= 0 else c["red"])
        self._saved_card.set_value(format_eur(total_saldo), c["primary"] if total_saldo >= 0 else c["red"])
        self._saved_card.set_hint(f"Summe über {n} Monate")

        # Line chart: income / spending / balance.
        out_series = [p.fixed_cents + p.variable_cents for p in points]
        line_series = [
            ("Einnahmen", [p.income_cents for p in points], c["blue"]),
            ("Ausgaben", out_series, c["amber"]),
            ("Saldo", [p.remaining_cents for p in points], c["green"]),
        ]
        self._line_canvas.line_series(labels, line_series)
        self._line_canvas.setAccessibleDescription(
            f"Ø Einnahmen {format_eur(avg_income)}, Ø Ausgaben {format_eur(avg_out)}, "
            f"Ø Saldo {format_eur(avg_saldo)} über {n} Monate.")
        self._fill_line_legend(line_series)

        # Stacked category bars.
        cat_labels, per_month = history.category_series(points, top_n=6)
        cycle = theme.chart_colors(c)
        bar_series = [(cat, per_month[cat], cycle[i % len(cycle)])
                      for i, cat in enumerate(cat_labels)]
        self._bar_canvas.bars_stacked(labels, bar_series)
        self._fill_bar_legend(cat_labels, cycle)

    def _fill_line_legend(self, line_series) -> None:
        while self._line_legend_layout.count():
            item = self._line_legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for name, values, color in line_series:
            total = format_eur_short(sum(values))
            self._line_legend_layout.addWidget(
                self._dot_label(f"{name} · Σ {total}", color))
        self._line_legend_layout.addStretch(1)

    def _fill_bar_legend(self, cat_labels, cycle) -> None:
        while self._bar_legend_layout.count():
            item = self._bar_legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, cat in enumerate(cat_labels):
            r, col = divmod(i, 3)
            self._bar_legend_layout.addWidget(
                self._dot_label(cat, cycle[i % len(cycle)]), r, col)

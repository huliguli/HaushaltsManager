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
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules import annual, dates, forecast, history
from modules.money import format_eur, format_eur_short
from ui import theme
from ui.views.base_view import BaseView
from ui.widgets.chart_canvas import ChartCanvas
from ui.widgets.common import StatCard, align_table_headers, heading, muted

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
        container.setObjectName("ScrollBody")
        # Scoped by object name on purpose: a selector-less rule
        # would cascade onto every card inside and blank its fill.
        container.setStyleSheet("QWidget#ScrollBody { background: transparent; }")
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
        line_hint = QLabel("Klick auf einen Monat öffnet dessen Buchungen im Haushaltsbuch.")
        line_hint.setObjectName("Faint")
        line_body.addWidget(line_hint)
        self._body.addWidget(self._line_card)

        # Forward projection card ("Blick nach vorn"): the balance line
        # continues past today as a dashed forecast, drop-off months marked.
        self._forecast_card, fc_body = self._chart_card("Blick nach vorn: Saldo-Prognose")
        self._forecast_note = QLabel("")
        self._forecast_note.setObjectName("Muted")
        self._forecast_note.setWordWrap(True)
        fc_body.addWidget(self._forecast_note)
        self._forecast_canvas = ChartCanvas(c, width=6.6, height=2.9)
        self._forecast_canvas.setMinimumHeight(250)
        self._forecast_canvas.setAccessibleName("Saldo-Prognose für die kommenden Monate")
        fc_body.addWidget(self._forecast_canvas)
        events_wrap = QWidget()
        self._forecast_events_layout = QVBoxLayout(events_wrap)
        self._forecast_events_layout.setContentsMargins(0, 6, 0, 0)
        self._forecast_events_layout.setSpacing(4)
        fc_body.addWidget(events_wrap)
        self._body.addWidget(self._forecast_card)

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

        # Jahresübersicht card: whole calendar years with YoY comparison,
        # savings rate and the category × month matrix (v3.2.0).
        self._year_card, year_body = self._chart_card("Jahresübersicht")
        year_head = QHBoxLayout()
        self._year_note = QLabel("")
        self._year_note.setObjectName("Muted")
        self._year_note.setWordWrap(True)
        year_head.addWidget(self._year_note, 1)
        year_head.addWidget(self._range_label("Jahr"))
        self._year_combo = QComboBox()
        self._year_combo.setAccessibleName("Jahr für die Jahresübersicht")
        self._year_combo.currentIndexChanged.connect(self._on_year_changed)
        year_head.addWidget(self._year_combo)
        year_body.addLayout(year_head)

        self._year_kpis = QWidget()
        year_kpi_layout = QHBoxLayout(self._year_kpis)
        year_kpi_layout.setContentsMargins(0, 4, 0, 0)
        year_kpi_layout.setSpacing(16)
        self._year_income = StatCard("Einnahmen", c["blue"])
        self._year_expenses = StatCard("Ausgaben", c["amber"])
        self._year_saldo = StatCard("Saldo (gespart)", c["green"])
        self._year_rate = StatCard("Sparquote", c["primary"])
        for card in (self._year_income, self._year_expenses,
                     self._year_saldo, self._year_rate):
            year_kpi_layout.addWidget(card, 1)
        year_body.addWidget(self._year_kpis)

        self._matrix = QTableWidget(0, 14)
        self._matrix.setHorizontalHeaderLabels(
            ["Kategorie"] + [dates.month_name(m)[:3] for m in range(1, 13)] + ["Summe"])
        self._matrix.verticalHeader().setVisible(False)
        self._matrix.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._matrix.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._matrix.setAlternatingRowColors(True)
        self._matrix.setShowGrid(False)
        self._matrix.verticalHeader().setDefaultSectionSize(28)
        self._matrix.setMinimumHeight(160)
        self._matrix.setMaximumHeight(320)
        self._matrix.setAccessibleName("Ausgaben je Kategorie und Monat")
        year_body.addWidget(self._matrix)
        self._body.addWidget(self._year_card)
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

    def _on_year_changed(self) -> None:
        self._refresh_year_card()

    def _drill_month(self, index: int) -> None:
        """Chart click: open the Haushaltsbuch on the clicked month."""
        points = getattr(self, "_points", [])
        if 0 <= index < len(points):
            p = points[index]
            self.ctx.request_drilldown(p.year, p.month, "")

    def on_theme_changed(self) -> None:
        c = self.ctx.colors
        self._line_canvas.set_colors(c)
        self._bar_canvas.set_colors(c)
        self._forecast_canvas.set_colors(c)
        self.refresh()

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        c = self.ctx.colors
        points = history.monthly_series(
            self.ctx.income, self.ctx.fixed, self.ctx.expenses, self.ctx.var_income,
            self.ctx.summaries, months=self._months, ref=date.today())
        labels = [p.short_label for p in points]

        self._points = points  # month lookup for the chart drilldown
        self._refresh_year_card()

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
            self._forecast_canvas.saldo_forecast([], [], [], c["primary"])
            self._forecast_note.setText(
                "Sobald Einnahmen und Fixkosten erfasst sind, zeigt die "
                "Prognose hier den voraussichtlichen Saldo der kommenden Monate.")
            self._fill_forecast_events([])
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
        self._line_canvas.line_series(labels, line_series, on_month=self._drill_month)
        self._line_canvas.setAccessibleDescription(
            f"Ø Einnahmen {format_eur(avg_income)}, Ø Ausgaben {format_eur(avg_out)}, "
            f"Ø Saldo {format_eur(avg_saldo)} über {n} Monate.")
        self._fill_line_legend(line_series)

        # Stacked category bars.
        cat_labels, per_month = history.category_series(points, top_n=6)
        cycle = theme.chart_colors(c)
        bar_series = [(cat, per_month[cat], cycle[i % len(cycle)])
                      for i, cat in enumerate(cat_labels)]
        self._bar_canvas.bars_stacked(labels, bar_series, on_month=self._drill_month)
        self._fill_bar_legend(cat_labels, cycle)

        # Forward projection: same horizon as the selected range, connected to
        # the last months of real history (solid) as a dashed continuation.
        fpoints = forecast.project(
            self.ctx.income, self.ctx.fixed, self.ctx.expenses, months=self._months)
        tail = points[-6:]
        f_labels = [p.short_label for p in tail] + [p.short_label for p in fpoints]
        actual = [p.remaining_cents for p in tail]
        future = [p.remaining_cents for p in fpoints]
        event_idx = [len(tail) + i for i, p in enumerate(fpoints) if p.events]
        self._forecast_canvas.saldo_forecast(
            f_labels, actual, future, c["primary"], event_idx)
        avg_future = sum(future) // max(1, len(future))
        self._forecast_note.setText(
            f"Voraussichtlicher Saldo: Ø {format_eur(avg_future)} pro Monat, "
            f"kumuliert nach {len(fpoints)} Monaten {format_eur(fpoints[-1].cumulative_cents)}. "
            "Grundlage: feste Einnahmen, Fixkosten mit ihren Enddaten, wiederkehrende "
            "Ausgaben sowie der Durchschnitt der einmaligen Ausgaben der letzten "
            f"{forecast.ONEOFF_HISTORY_MONTHS} Monate.")
        self._forecast_canvas.setAccessibleDescription(
            f"Prognose: durchschnittlich {format_eur(avg_future)} Saldo pro Monat "
            f"über {len(fpoints)} Monate.")
        self._fill_forecast_events(fpoints)

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

    def _fill_forecast_events(self, fpoints) -> None:
        """List the months where fixed costs start or drop off (max 8 rows)."""
        while self._forecast_events_layout.count():
            item = self._forecast_events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        c = self.ctx.colors
        rows = [(p, e) for p in fpoints for e in p.events]
        if not rows:
            if fpoints:
                note = QLabel("Im gewählten Zeitraum endet oder beginnt kein befristeter Posten.")
                note.setObjectName("Faint")
                self._forecast_events_layout.addWidget(note)
            return
        for p, event in rows[:8]:
            text = (f"{p.label}: {event} — Fixkosten dann {format_eur(p.fixed_cents)}, "
                    f"Saldo {format_eur(p.remaining_cents)}")
            self._forecast_events_layout.addWidget(self._dot_label(text, c["amber"]))
        if len(rows) > 8:
            more = QLabel(f"… und {len(rows) - 8} weitere Änderungen im Zeitraum.")
            more.setObjectName("Faint")
            self._forecast_events_layout.addWidget(more)

    # -- Jahresübersicht ------------------------------------------------------
    def _refresh_year_card(self) -> None:
        c = self.ctx.colors
        years = annual.available_years(self.ctx.expenses, self.ctx.var_income)
        current = [self._year_combo.itemData(i) for i in range(self._year_combo.count())]
        if years != current:
            selected = self._year_combo.currentData()
            blocked = self._year_combo.blockSignals(True)
            self._year_combo.clear()
            for y in years:
                self._year_combo.addItem(str(y), y)
            if selected in years:
                self._year_combo.setCurrentIndex(years.index(selected))
            self._year_combo.blockSignals(blocked)
        year = self._year_combo.currentData() or date.today().year

        ov = annual.build(self.ctx.income, self.ctx.fixed, self.ctx.expenses,
                          self.ctx.var_income, year)
        prev = annual.build(self.ctx.income, self.ctx.fixed, self.ctx.expenses,
                            self.ctx.var_income, year - 1)
        has_prev = prev.has_data

        covered = ("ganzes Jahr" if ov.months_covered == 12
                   else f"Januar bis {dates.month_name(max(1, ov.months_covered))}")
        note = f"Kalenderjahr {year} ({covered})"
        if has_prev:
            note += f" im Vergleich zu {year - 1}"
        note += ". Der Jahresbericht als Excel/PDF steht unter Import / Export bereit."
        self._year_note.setText(note)

        def yoy(card: StatCard, cur: int, prev_val: int, *, good_up: bool) -> None:
            if not has_prev or cur == prev_val:
                card.set_delta("", c["text_faint"])
                return
            d = cur - prev_val
            arrow = "▲" if d > 0 else "▼"
            good = (d > 0) == good_up
            card.set_delta(f"{arrow} {format_eur(abs(d))} ggü. Vorjahr",
                           c["green"] if good else c["red"])

        self._year_income.set_value(format_eur(ov.income_cents), c["text"])
        self._year_income.set_hint(f"{ov.months_covered} Monate")
        yoy(self._year_income, ov.income_cents, prev.income_cents, good_up=True)
        self._year_expenses.set_value(format_eur(ov.expenses_cents), c["text"])
        self._year_expenses.set_hint("Fix + variabel")
        yoy(self._year_expenses, ov.expenses_cents, prev.expenses_cents, good_up=False)
        saldo_color = c["green"] if ov.remaining_cents >= 0 else c["red"]
        self._year_saldo.set_accent(saldo_color)
        self._year_saldo.set_value(format_eur(ov.remaining_cents), saldo_color)
        self._year_saldo.set_hint("Einnahmen − alle Ausgaben")
        yoy(self._year_saldo, ov.remaining_cents, prev.remaining_cents, good_up=True)

        rate = ov.savings_rate
        if rate is None:
            self._year_rate.set_value("–", c["text_faint"])
            self._year_rate.set_hint("Keine Einnahmen erfasst")
            self._year_rate.set_delta("", c["text_faint"])
        else:
            rate_color = c["green"] if rate >= 0 else c["red"]
            self._year_rate.set_value(f"{rate * 100:.1f} %".replace(".", ","), rate_color)
            self._year_rate.set_hint("Gesparter Anteil der Einnahmen")
            if has_prev and prev.savings_rate is not None:
                d = (rate - prev.savings_rate) * 100
                if abs(d) >= 0.05:
                    arrow = "▲" if d > 0 else "▼"
                    txt = f"{arrow} {abs(d):.1f} Prozentpunkte ggü. Vorjahr".replace(".", ",")
                    self._year_rate.set_delta(txt, c["green"] if d > 0 else c["red"])
                else:
                    self._year_rate.set_delta("", c["text_faint"])
            else:
                self._year_rate.set_delta("", c["text_faint"])

        self._fill_matrix(ov)

    def _fill_matrix(self, ov) -> None:
        categories, per_month = annual.category_matrix(ov)
        self._matrix.setRowCount(len(categories))
        for r, cat in enumerate(categories):
            name = QTableWidgetItem(cat)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._matrix.setItem(r, 0, name)
            for m in range(12):
                cents = per_month[cat][m]
                cell = QTableWidgetItem(format_eur_short(cents) if cents else "–")
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._matrix.setItem(r, 1 + m, cell)
            total = QTableWidgetItem(format_eur(sum(per_month[cat])))
            total.setFlags(total.flags() & ~Qt.ItemFlag.ItemIsEditable)
            total.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._matrix.setItem(r, 13, total)
        header = self._matrix.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 14):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        align_table_headers(self._matrix, right_cols=tuple(range(1, 14)))
        self._matrix.setVisible(bool(categories))

    def _fill_bar_legend(self, cat_labels, cycle) -> None:
        while self._bar_legend_layout.count():
            item = self._bar_legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, cat in enumerate(cat_labels):
            r, col = divmod(i, 3)
            self._bar_legend_layout.addWidget(
                self._dot_label(cat, cycle[i % len(cycle)]), r, col)

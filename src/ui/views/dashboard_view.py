"""Dashboard: navigable month summary, availability, category budgets, breakdown
chart and the fixed-cost drop-off timeline.

The view rebuilds its body on every ``refresh()`` so it always reflects the
latest data and the current theme. The month navigator lets the user step back
through history; every card then shows the selected month plus its change versus
the previous month. Numbers come from the budget service and the timeline
calculator; nothing is computed inline here.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from modules import dates, savings_goals
from modules.calculator import timeline
from modules.money import format_eur, format_eur_short
from ui import theme
from ui.budget_dialog import CategoryBudgetDialog
from ui.goal_dialogs import SavingsGoalsManageDialog
from ui.views.base_view import BaseView
from ui.widgets.chart_canvas import ChartCanvas
from ui.widgets.common import StatCard, clear_layout, heading, muted, primary_button
from ui.widgets.month_nav import MonthNavigator


class DashboardView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        today = date.today()
        self._year, self._month = today.year, today.month

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._body = QVBoxLayout(self._container)
        self._body.setContentsMargins(30, 26, 30, 26)
        self._body.setSpacing(18)
        scroll.setWidget(self._container)

    # -- month selection ----------------------------------------------------
    def _on_month(self, year: int, month: int) -> None:
        self._year, self._month = year, month
        self.refresh()

    def _is_current_month(self) -> bool:
        today = date.today()
        return (self._year, self._month) == (today.year, today.month)

    def _prev_month(self) -> tuple[int, int]:
        return dates.shift_month(self._year, self._month, -1)

    # -- build --------------------------------------------------------------
    def refresh(self) -> None:
        clear_layout(self._body)
        c = self.ctx.colors
        ov = self.ctx.overview(self._year, self._month)
        py, pm = self._prev_month()
        prev = self.ctx.overview(py, pm)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(heading("Dashboard"))
        title_box.addWidget(muted("Monatsübersicht mit Vergleich zum Vormonat."))
        header.addLayout(title_box)
        header.addStretch(1)
        nav = MonthNavigator(c, self._year, self._month, allow_future=False)
        nav.month_changed.connect(self._on_month)
        self._nav = nav  # exposed via month_navigator() for the keyboard layer
        header.addWidget(nav)
        self._body.addLayout(header)

        # First start: an empty database shows zeros everywhere — put the
        # setup wizard front and centre instead of leaving a dead dashboard.
        from modules.seed import database_is_empty
        if database_is_empty(self.ctx.db):
            self._body.addWidget(self._onboarding_card(c))

        self._body.addWidget(self._stat_row(ov, prev, c))
        self._body.addWidget(self._availability_and_chart(ov, c))
        budget_panel = self._budget_panel(ov, c)
        if budget_panel is not None:
            self._body.addWidget(budget_panel)
        self._body.addWidget(self._goals_panel(c))
        self._body.addWidget(self._timeline_panel(ov, c))
        self._body.addStretch(1)

    def month_navigator(self):
        return getattr(self, "_nav", None)

    # -- onboarding ----------------------------------------------------------
    def _onboarding_card(self, c) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(22, 20, 22, 20)
        box.setSpacing(8)
        title = QLabel("Willkommen! In 2 Minuten startklar")
        title.setObjectName("H2")
        box.addWidget(title)
        text = QLabel(
            "Es sind noch keine Daten vorhanden. Der Assistent fragt deine "
            "Einnahmen und die wichtigsten Fixkosten ab – danach zeigt das "
            "Dashboard deine echte Monatsübersicht. Alternativ kannst du unter "
            "Import / Export direkt einen Kontoauszug einlesen.")
        text.setObjectName("Muted")
        text.setWordWrap(True)
        box.addWidget(text)
        row = QHBoxLayout()
        # Inline-filled primary button: the dashboard body sits on a
        # transparent scroll container where the global #Primary fill vanishes.
        btn = primary_button("Jetzt einrichten", c)
        btn.clicked.connect(self._run_wizard)
        row.addWidget(btn)
        row.addStretch(1)
        box.addLayout(row)
        return card

    def _run_wizard(self) -> None:
        from ui.wizard import run_wizard
        run_wizard(self.ctx, self)
        self.ctx.notify_changed()

    # -- sections -----------------------------------------------------------
    def _delta(self, cur: int, prev: int, c, *, good_up: bool) -> tuple[str, str]:
        """(text, colour) for a change-vs-previous line; empty text when equal."""
        d = cur - prev
        if d == 0:
            return "", c["text_faint"]
        arrow = "▲" if d > 0 else "▼"
        good = (d > 0) == good_up
        color = c["green"] if good else c["red"]
        return f"{arrow} {format_eur(abs(d))} ggü. Vormonat", color

    def _stat_row(self, ov, prev, c) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        income = StatCard("Einnahmen", c["blue"])
        income.set_value(format_eur(ov.income_cents), c["text"])
        income.set_hint("Aktive Einnahmequellen")
        income.set_delta(*self._delta(ov.income_cents, prev.income_cents, c, good_up=True))

        fixed = StatCard("Fixkosten", c["amber"])
        fixed.set_value(format_eur(ov.fixed_cents), c["text"])
        fixed.set_hint(f"davon Kredite {format_eur(ov.credits_cents)}")

        variable = StatCard("Variable Ausgaben", c["grey"])
        variable.set_value(format_eur(ov.variable_cents), c["text"])
        variable.set_hint("Diesen Monat erfasst")
        variable.set_delta(*self._delta(ov.variable_cents, prev.variable_cents, c, good_up=False))

        remaining = StatCard("Verbleibend", c["green"])
        rem = ov.after_all_cents
        remaining.set_accent(c["green"] if rem >= 0 else c["red"])
        remaining.set_value(format_eur(rem), c["green"] if rem >= 0 else c["red"])
        remaining.set_hint("Nach Fix- und variablen Kosten")
        remaining.set_delta(*self._delta(rem, prev.after_all_cents, c, good_up=True))

        for card in (income, fixed, variable, remaining):
            layout.addWidget(card, 1)
        return row

    def _availability_and_chart(self, ov, c) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Availability panel
        panel = QFrame()
        panel.setObjectName("Card")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(22, 20, 22, 20)
        pl.setSpacing(14)
        pl.addWidget(self._panel_title("Verfügbarkeit"))

        pl.addLayout(self._avail_line(
            "Verfügbar nach Fixkosten", ov.after_fixed_cents,
            c["green"] if ov.after_fixed_cents >= 0 else c["red"], big=True))
        pl.addLayout(self._avail_line(
            "Verfügbar nach allem", ov.after_all_cents,
            c["green"] if ov.after_all_cents >= 0 else c["red"]))
        big_purchase = max(0, ov.after_all_cents)
        line = self._avail_line("Budget für Großanschaffungen", big_purchase, c["blue"])
        pl.addLayout(line)
        # Annual projection uses the recurring surplus only — a one-off credit
        # this month must not be multiplied across the whole year.
        yearly = max(0, ov.recurring_income_cents - ov.fixed_cents - ov.variable_cents) * 12
        hint = QLabel(f"≈ {format_eur(yearly)} pro Jahr ansparbar")
        hint.setObjectName("Faint")
        pl.addWidget(hint)
        pl.addStretch(1)
        layout.addWidget(panel, 1)

        # Expense breakdown donut
        chart_panel = QFrame()
        chart_panel.setObjectName("Card")
        cl = QVBoxLayout(chart_panel)
        cl.setContentsMargins(22, 20, 22, 16)
        cl.addWidget(self._panel_title("Ausgaben nach Kategorie"))
        canvas = ChartCanvas(c, width=4.2, height=2.6)
        canvas.setMinimumHeight(230)
        canvas.setAccessibleName("Ausgaben nach Kategorie in diesem Monat")
        by_cat = ov.expenses_by_category
        if by_cat:
            labels = list(by_cat.keys())
            values = [v / 100.0 for v in by_cat.values()]
            cycle = theme.chart_colors(c)
            slice_colors = [cycle[i % len(cycle)] for i in range(len(labels))]
            canvas.donut(labels, values, slice_colors,
                         center_text=format_eur_short(ov.variable_cents))
            top = ", ".join(f"{k} {format_eur(v)}" for k, v in list(by_cat.items())[:3])
            canvas.setAccessibleDescription(f"Größte Kategorien: {top}.")
        else:
            canvas.donut([], [], [])
        cl.addWidget(canvas)
        # Legend
        if by_cat:
            legend = self._donut_legend(by_cat, c)
            cl.addWidget(legend)
        layout.addWidget(chart_panel, 1)
        return row

    # -- category budgets ---------------------------------------------------
    def _budget_panel(self, ov, c) -> QWidget | None:
        """Progress bars of spend vs. monthly limit; only for budgeted categories.

        Returns ``None`` on a non-current month with no budgets set, so past
        months are not cluttered with an empty budgets card.
        """
        budgets = self.ctx.budgets.all()
        panel = QFrame()
        panel.setObjectName("Card")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(22, 20, 22, 20)
        pl.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(self._panel_title("Budgets"))
        head.addStretch(1)
        edit = QPushButton("Budgets festlegen" if not budgets else "Bearbeiten")
        edit.setObjectName("Link")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(self._open_budgets)
        head.addWidget(edit)
        pl.addLayout(head)

        if not budgets:
            hint = QLabel("Lege Monatslimits pro Kategorie fest, um Ausgaben im Blick zu behalten.")
            hint.setObjectName("Faint")
            hint.setWordWrap(True)
            pl.addWidget(hint)
            return panel

        for cat in sorted(budgets, key=lambda k: budgets[k], reverse=True):
            limit = budgets[cat]
            spent = ov.expenses_by_category.get(cat, 0)
            pl.addWidget(self._budget_row(cat, spent, limit, c))
        return panel

    def _budget_row(self, cat: str, spent: int, limit: int, c) -> QWidget:
        wrap = QWidget()
        box = QVBoxLayout(wrap)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)

        ratio = spent / limit if limit else 0
        key = "green" if ratio < 0.8 else ("amber" if ratio < 1.0 else "red")
        color = theme.ampel_color(key, c)

        top = QHBoxLayout()
        name = QLabel(cat)
        name.setObjectName("Muted")
        pct = QLabel(f"{format_eur(spent)} / {format_eur(limit)} · {round(ratio * 100)} %")
        pct.setStyleSheet(f"color: {color}; font-weight: 600;")
        pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(pct)
        box.addLayout(top)

        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setRange(0, max(1, limit))
        bar.setValue(min(spent, limit))
        bar.setAccessibleName(f"Budget {cat}: {round(ratio * 100)} Prozent verbraucht")
        bar.setStyleSheet(
            f"QProgressBar {{ background: {c['surface_3']}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}")
        box.addWidget(bar)
        return wrap

    def _open_budgets(self) -> None:
        if CategoryBudgetDialog(self.ctx, self).exec():
            self.ctx.notify_changed()

    # -- savings goals --------------------------------------------------------
    def _goals_panel(self, c) -> QWidget:
        """Progress bars of the persisted savings goals (see modules.savings_goals)."""
        goals = self.ctx.goals.list()
        panel = QFrame()
        panel.setObjectName("Card")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(22, 20, 22, 20)
        pl.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(self._panel_title("Sparziele"))
        head.addStretch(1)
        manage = QPushButton("Sparziele anlegen" if not goals else "Verwalten")
        manage.setObjectName("Link")
        manage.setCursor(Qt.CursorShape.PointingHandCursor)
        manage.clicked.connect(self._open_goals)
        head.addWidget(manage)
        pl.addLayout(head)

        if not goals:
            hint = QLabel("Lege ein Sparziel mit Rate und Zielbetrag fest – der "
                          "Fortschritt wächst dann von allein mit.")
            hint.setObjectName("Faint")
            hint.setWordWrap(True)
            pl.addWidget(hint)
            return panel

        for goal in goals:
            pl.addWidget(self._goal_row(goal, c))
        return panel

    def _goal_row(self, goal, c) -> QWidget:
        p = savings_goals.compute(goal)
        wrap = QWidget()
        box = QVBoxLayout(wrap)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)

        color = c["green"] if p.reached else c["blue"]
        top = QHBoxLayout()
        name = QLabel(goal.name)
        name.setObjectName("Muted")
        state = QLabel(f"{format_eur(p.saved_cents)} / {format_eur(p.target_cents)}"
                       f" · {round(p.ratio * 100)} %")
        state.setStyleSheet(f"color: {color}; font-weight: 600;")
        state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(state)
        box.addLayout(top)

        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setRange(0, 1000)
        bar.setValue(round(p.ratio * 1000))
        bar.setAccessibleName(
            f"Sparziel {goal.name}: {round(p.ratio * 100)} Prozent erreicht")
        bar.setStyleSheet(
            f"QProgressBar {{ background: {c['surface_3']}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}")
        box.addWidget(bar)

        sub = QLabel(f"{format_eur(goal.monthly_cents)} / Monat · "
                     f"{savings_goals.eta_label(p)}")
        sub.setObjectName("Faint")
        box.addWidget(sub)
        return wrap

    def _open_goals(self) -> None:
        dlg = SavingsGoalsManageDialog(self.ctx, self)
        dlg.exec()
        if dlg.changed:
            self.ctx.notify_changed()

    def _timeline_panel(self, ov, c) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(22, 20, 22, 22)
        pl.setSpacing(8)
        pl.addWidget(self._panel_title("Fixkosten-Abbau"))
        sub = QLabel("Wann fällt welche Kosten weg – und was bleibt dann übrig.")
        sub.setObjectName("Faint")
        pl.addWidget(sub)
        pl.addSpacing(6)

        # Future dropoff projection uses recurring income only (a one-off credit
        # this month must not lift the projected available amount).
        result = timeline.build(ov.recurring_income_cents, self.ctx.fixed.list())

        # Current state line.
        pl.addLayout(self._timeline_row(
            "Jetzt", f"Fixkosten {format_eur(result.current_fixed_total_cents)}",
            f"verfügbar {format_eur(result.current_available_cents)}", c["blue"], c, bold=True))

        if not result.events:
            note = QLabel("Keine befristeten Fixkosten – es fällt aktuell nichts planbar weg.")
            note.setObjectName("Muted")
            pl.addSpacing(6)
            pl.addWidget(note)
            return panel

        for ev in result.events:
            names = ", ".join(d.name for d in ev.dropped)
            left = f"{ev.label}"
            mid = f"{names} fällt weg  (−{format_eur(ev.dropped_amount_cents)})"
            right = (f"Fix {format_eur(ev.new_fixed_total_cents)} · "
                     f"verfügbar {format_eur(ev.available_after_fixed_cents)}")
            pl.addLayout(self._timeline_event_row(left, mid, right, c))
        return panel

    # -- small builders -----------------------------------------------------
    def _panel_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("H2")
        return lbl

    def _avail_line(self, label: str, cents: int, color: str, big: bool = False) -> QHBoxLayout:
        row = QHBoxLayout()
        name = QLabel(label)
        name.setObjectName("Muted")
        value = QLabel(format_eur(cents))
        value.setStyleSheet(
            f"color: {color}; font-weight: 700; font-size: {22 if big else 16}px;")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(value)
        return row

    def _donut_legend(self, by_cat: dict, c) -> QWidget:
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        cycle = theme.chart_colors(c)
        total = sum(by_cat.values()) or 1
        for i, (cat, val) in enumerate(by_cat.items()):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {cycle[i % len(cycle)]}; font-size: 13px;")
            # Show the share in percent so the legend conveys the split without
            # relying on colour alone (WCAG 1.4.1).
            text = QLabel(f"{cat}  {format_eur(val)} · {round(val * 100 / total)} %")
            text.setObjectName("Faint")
            r, col = divmod(i, 2)
            cell = QHBoxLayout()
            cell.setSpacing(6)
            cell.addWidget(dot)
            cell.addWidget(text)
            cell.addStretch(1)
            holder = QWidget()
            holder.setLayout(cell)
            grid.addWidget(holder, r, col)
        return wrap

    def _timeline_row(self, left: str, mid: str, right: str, color: str, c,
                      bold: bool = False) -> QHBoxLayout:
        row = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        l = QLabel(f"<b>{left}</b>" if bold else left)
        l.setMinimumWidth(90)
        m = QLabel(mid)
        m.setObjectName("Muted")
        r = QLabel(right)
        r.setStyleSheet(f"color: {c['text']}; font-weight: 600;")
        r.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(dot)
        row.addWidget(l)
        row.addWidget(m)
        row.addStretch(1)
        row.addWidget(r)
        return row

    def _timeline_event_row(self, left: str, mid: str, right: str, c) -> QHBoxLayout:
        return self._timeline_row(left, mid, right, c["green"], c)

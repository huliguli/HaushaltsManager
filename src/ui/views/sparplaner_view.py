"""Sparplaner: a savings planner with two directions.

* "Sparrate vorgeben": enter a monthly rate + term -> final amount, interest,
  and how much of the monthly "Verbleibend" is left after saving.
* "Sparziel vorgeben": enter a target + term -> the monthly rate needed, plus
  the same budget view.

Both optionally take a starting capital and an annual interest rate (compound).
The remaining-budget check uses the live dashboard "Verbleibend" so the user
sees immediately whether a plan fits their month.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.calculator import savings
from modules.money import format_eur
from ui import theme
from ui.views.base_view import BaseView
from ui.widgets.common import align_table_headers, clear_layout, heading, muted
from ui.widgets.inputs import MoneyLineEdit, labelled


def _percent_field(value: float = 0.0) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(0.0, 25.0)
    box.setDecimals(2)
    box.setSingleStep(0.1)
    box.setSuffix(" %")
    box.setValue(value)
    return box


def _int_field(minimum: int, maximum: int, value: int, suffix: str = "") -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    if suffix:
        box.setSuffix(suffix)
    return box


def _metric(label: str, value: str, color: str) -> QFrame:
    chip = QFrame()
    chip.setObjectName("Panel")
    layout = QVBoxLayout(chip)
    layout.setContentsMargins(15, 12, 15, 12)
    layout.setSpacing(3)
    name = QLabel(label)
    name.setObjectName("CardTitle")
    val = QLabel(value)
    val.setStyleSheet(f"color: {color}; font-size: 19px; font-weight: 700;")
    layout.addWidget(name)
    layout.addWidget(val)
    return chip


def _feasibility(monthly_cents: int, available_cents: int) -> tuple[str, str]:
    """Traffic-light status of a savings rate against the monthly Verbleibend."""
    if monthly_cents <= 0:
        return "gut", "Kein Sparbetrag nötig"
    if available_cents <= 0 or monthly_cents > available_cents:
        return "riskant", "Über dem Verbleibend"
    ratio = monthly_cents / available_cents
    if ratio <= 0.75:
        return "gut", "Gut machbar"
    if ratio <= 1.0:
        return "knapp", "Knapp"
    return "riskant", "Über dem Verbleibend"


class SparplanerView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 26, 30, 24)
        outer.setSpacing(6)
        outer.addWidget(heading("Sparplaner"))
        outer.addWidget(muted(
            "Sparplan aus Sparrate oder Sparziel berechnen – mit Zinsen und Budget-Check."))

        root = QHBoxLayout()
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(18)
        outer.addLayout(root, 1)

        # -- form column (scrollable so it never clips on small windows) -----
        form_wrap = QFrame()
        form_wrap.setObjectName("Card")
        self.form = QVBoxLayout(form_wrap)
        self.form.setContentsMargins(20, 20, 20, 20)
        self.form.setSpacing(12)
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_scroll.setMaximumWidth(380)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        form_scroll.setWidget(form_wrap)
        root.addWidget(form_scroll)

        # -- results column --------------------------------------------------
        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll.setFrameShape(QFrame.Shape.NoFrame)
        results_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.results = QVBoxLayout(container)
        self.results.setContentsMargins(2, 2, 2, 14)
        self.results.setSpacing(14)
        results_scroll.setWidget(container)
        root.addWidget(results_scroll, 1)

        # -- inputs ----------------------------------------------------------
        self.mode_rate = QRadioButton("Sparrate vorgeben")
        self.mode_goal = QRadioButton("Sparziel vorgeben")
        self.mode_rate.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_rate)
        mode_group.addButton(self.mode_goal)
        mode_box = QVBoxLayout()
        mode_box.setSpacing(4)
        mode_box.addWidget(self.mode_rate)
        mode_box.addWidget(self.mode_goal)
        mode_wrap = QWidget()
        mode_wrap.setLayout(mode_box)

        self.rate_field = MoneyLineEdit(20000)        # 200 €/Monat
        self.goal_field = MoneyLineEdit(1000000)      # 10.000 €
        self.months = _int_field(1, 600, 24, " Mon.")
        self.interest = _percent_field(0.0)
        self.start = MoneyLineEdit(0)

        self._rate_row = labelled("Sparrate / Monat", self.rate_field)
        self._goal_row = labelled("Sparziel", self.goal_field)

        self.error = QLabel("")
        self.error.setStyleSheet("color: #d6453d; font-size: 12px;")
        self.error.setWordWrap(True)
        self.error.hide()

        self.form.addWidget(labelled("Modus", mode_wrap))
        self.form.addWidget(self._rate_row)
        self.form.addWidget(self._goal_row)
        self.form.addWidget(labelled("Laufzeit", self.months))
        self.form.addWidget(labelled("Zinssatz p.a. (optional)", self.interest))
        self.form.addWidget(labelled("Startkapital (optional)", self.start))
        go = QPushButton("Berechnen")
        go.setObjectName("Primary")
        go.clicked.connect(self._compute)
        self.form.addWidget(go)
        self.form.addWidget(self.error)
        self.form.addStretch(1)

        self.mode_rate.toggled.connect(self._on_mode)
        self._on_mode()
        self._compute()

    def _on_mode(self) -> None:
        rate_mode = self.mode_rate.isChecked()
        self._rate_row.setVisible(rate_mode)
        self._goal_row.setVisible(not rate_mode)
        self._compute()

    def _show_error(self, message: str) -> None:
        clear_layout(self.results)
        self.error.setText(message)
        self.error.show()

    def _metric_row(self, metrics: list[tuple[str, str, str]]) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        for label, value, color in metrics:
            layout.addWidget(_metric(label, value, color))
        layout.addStretch(1)
        return row

    def _compute(self) -> None:
        self.error.hide()
        months = self.months.value()
        rate_pct = self.interest.value()
        start = self.start.cents() or 0
        if start < 0:
            return self._show_error("Das Startkapital darf nicht negativ sein.")
        try:
            if self.mode_rate.isChecked():
                monthly = self.rate_field.cents()
                if monthly is None:
                    return self._show_error("Bitte eine gültige Sparrate eingeben.")
                if monthly < 0:
                    return self._show_error("Die Sparrate darf nicht negativ sein.")
                res = savings.from_rate(monthly, months, rate_pct, start)
            else:
                goal = self.goal_field.cents()
                if goal is None:
                    return self._show_error("Bitte ein gültiges Sparziel eingeben.")
                if goal <= 0:
                    return self._show_error("Bitte ein Sparziel größer als 0 eingeben.")
                res = savings.from_goal(goal, months, rate_pct, start)
        except ValueError as exc:
            return self._show_error(str(exc))

        c = self.ctx.colors
        disposable = self.ctx.overview().after_all_cents
        remaining = disposable - res.monthly_cents
        status, label = _feasibility(res.monthly_cents, disposable)
        badge_color = {"gut": c["green"], "knapp": c["amber"], "riskant": c["red"]}[status]

        clear_layout(self.results)

        badge = QLabel(f"  {label}  ")
        badge.setStyleSheet(
            f"color: {theme.on_color(badge_color)}; background: {badge_color}; "
            f"border-radius: 9px; padding: 8px 14px; font-weight: 700; font-size: 15px;")
        badge_row = QHBoxLayout()
        badge_row.addWidget(badge)
        badge_row.addStretch(1)
        badge_wrap = QWidget()
        badge_wrap.setLayout(badge_row)
        self.results.addWidget(badge_wrap)

        contributed = res.start_cents + res.deposited_cents
        if self.mode_goal.isChecked():
            self.results.addWidget(self._metric_row([
                ("Benötigte Sparrate / Monat", format_eur(res.monthly_cents), c["primary"]),
                ("Endkapital", format_eur(res.final_cents), c["text"]),
            ]))
            self.results.addWidget(self._metric_row([
                ("Eingezahlt gesamt", format_eur(contributed), c["blue"]),
                ("Zinsertrag", format_eur(res.interest_cents), c["green"]),
            ]))
        else:
            self.results.addWidget(self._metric_row([
                ("Endkapital", format_eur(res.final_cents), c["primary"]),
                ("Eingezahlt gesamt", format_eur(contributed), c["text"]),
                ("Zinsertrag", format_eur(res.interest_cents), c["green"]),
            ]))

        self.results.addWidget(self._metric_row([
            ("Verfügbar (Verbleibend)", format_eur(disposable), c["blue"]),
            ("Verbleibend nach Sparrate", format_eur(remaining),
             c["green"] if remaining >= 0 else c["red"]),
        ]))

        if res.goal_reached_by_start and res.start_cents > 0:
            note = QLabel("Dein Startkapital erreicht das Ziel bereits – es ist keine "
                          "monatliche Sparrate nötig.")
            note.setObjectName("Muted")
            note.setWordWrap(True)
            self.results.addWidget(note)
        elif res.start_cents > 0:
            note = QLabel(f"Inklusive Startkapital {format_eur(res.start_cents)}.")
            note.setObjectName("Faint")
            note.setWordWrap(True)
            self.results.addWidget(note)

        plan_title = QLabel("Verlauf")
        plan_title.setObjectName("H2")
        self.results.addWidget(plan_title)
        self.results.addWidget(self._schedule_table(res), 1)

    def _schedule_table(self, res: savings.SavingsResult) -> QTableWidget:
        rows = res.schedule
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["Monat", "Eingezahlt", "Zinsen", "Stand"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(28)
        for r, ms in enumerate(rows):
            # "Eingezahlt" here includes the starting capital for a true balance.
            paid = res.start_cents + ms.deposited_cents
            cells = [str(ms.month), format_eur(paid), format_eur(ms.interest_cents),
                     format_eur(ms.balance_cents)]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(r, col, item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(1, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        align_table_headers(table, right_cols=(1, 2, 3))
        return table

    def refresh(self) -> None:
        # Recompute on navigation/data change so the Verbleibend stays live.
        self._compute()

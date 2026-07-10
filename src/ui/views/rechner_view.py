"""Rechner: annuity, balloon, car and house financing calculators.

Each tab has an input form on the left and a results area on the right that is
rebuilt on every calculation (summary metric chips plus an amortisation or
comparison table). Inputs use the German money field and validate before
computing; errors are shown inline rather than thrown.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QCheckBox,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.calculator import annuity, auto, balloon, house
from modules.money import format_eur
from ui import plan_actions, theme
from ui.views.base_view import BaseView
from ui.widgets.common import (
    align_table_headers,
    clear_layout,
    compute_on_enter,
    heading,
    muted,
    primary_button,
)
from ui.widgets.inputs import MoneyLineEdit, labelled


# --- shared field helpers --------------------------------------------------
def _percent_field(value: float = 3.5) -> QDoubleSpinBox:
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


def _schedule_table(schedule, max_rows: int = 0) -> QTableWidget:
    rows = schedule if not max_rows else schedule[:max_rows]
    table = QTableWidget(len(rows), 5)
    table.setHorizontalHeaderLabels(["Monat", "Rate", "Tilgung", "Zinsen", "Restschuld"])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setDefaultSectionSize(28)
    for r, row in enumerate(rows):
        cells = [
            str(row.month), format_eur(row.payment_cents), format_eur(row.principal_cents),
            format_eur(row.interest_cents), format_eur(row.balance_cents),
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, col, item)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    for col in range(1, 5):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
    align_table_headers(table, right_cols=(1, 2, 3, 4))
    return table


class _CalcTab(QWidget):
    """Base layout: a form column and a scrollable results column."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        root = QHBoxLayout(self)
        root.setContentsMargins(2, 14, 2, 2)
        root.setSpacing(18)

        form_wrap = QFrame()
        form_wrap.setObjectName("Card")
        self.form = QVBoxLayout(form_wrap)
        self.form.setContentsMargins(20, 20, 20, 20)
        self.form.setSpacing(12)
        # The form can grow tall (e.g. the car tab's editable running costs), so
        # the input column scrolls instead of clipping on smaller windows.
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_scroll.setMaximumWidth(380)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        form_scroll.setWidget(form_wrap)
        root.addWidget(form_scroll)

        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll.setFrameShape(QFrame.Shape.NoFrame)
        results_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        results_container = QWidget()
        results_container.setStyleSheet("background: transparent;")
        self.results = QVBoxLayout(results_container)
        # Bottom inset so the amortisation table never sits flush against the
        # window edge (it stretches to fill the results column).
        self.results.setContentsMargins(2, 2, 2, 14)
        self.results.setSpacing(14)
        results_scroll.setWidget(results_container)
        root.addWidget(results_scroll, 1)

        self.error = QLabel("")
        self.error.setObjectName("ErrorText")
        self.error.setWordWrap(True)
        self.error.hide()
        self.form.addWidget(self.error)

        # Enter anywhere in the tab recalculates (every subclass provides
        # _compute); resolved at call time, so binding here covers all tabs.
        compute_on_enter(self, lambda: self._compute())

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

    def _plan_row(self, *, name: str, total_cents: int | None, monthly_cents: int,
                  term_months: int, interest_rate: float | None, category: str) -> QWidget:
        """A right-aligned 'add this loan to the Haushaltsbuch' action button."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        btn = primary_button("Als Kredit ins Haushaltsbuch", self.ctx.colors)
        btn.clicked.connect(lambda _=False: plan_actions.confirm_and_plan_credit(
            self, self.ctx, name=name, total_cents=total_cents, monthly_cents=monthly_cents,
            term_months=term_months, interest_rate=interest_rate, category=category))
        h.addWidget(btn)
        return row

    def refresh(self) -> None:
        pass


# --- Annuity tab -----------------------------------------------------------
class _AnnuityTab(_CalcTab):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.loan = MoneyLineEdit(2000000)
        self.down = MoneyLineEdit(0)
        self.rate = _percent_field(4.5)
        self.term = _int_field(1, 600, 60, " Mon.")
        self.form.insertWidget(0, labelled("Darlehensbetrag", self.loan))
        self.form.insertWidget(1, labelled("Anzahlung", self.down))
        self.form.insertWidget(2, labelled("Zinssatz p.a.", self.rate))
        self.form.insertWidget(3, labelled("Laufzeit", self.term))
        go = QPushButton("Berechnen")
        go.setObjectName("Primary")
        go.clicked.connect(self._compute)
        self.form.insertWidget(4, go)
        self.form.addStretch(1)
        self._compute()

    def _compute(self) -> None:
        self.error.hide()
        loan = self.loan.cents()
        down = self.down.cents() or 0
        if loan is None:
            return self._show_error("Bitte einen gültigen Darlehensbetrag eingeben.")
        principal = loan - down
        if principal <= 0:
            return self._show_error("Die Anzahlung ist so hoch wie der Darlehensbetrag.")
        res = annuity.compute(principal, self.rate.value(), self.term.value())
        c = self.ctx.colors
        clear_layout(self.results)
        self.results.addWidget(self._metric_row([
            ("Monatsrate", format_eur(res.monthly_payment_cents), c["primary"]),
            ("Gesamtkosten", format_eur(res.total_paid_cents), c["text"]),
            ("Gesamtzinsen", format_eur(res.total_interest_cents), c["amber"]),
        ]))
        self.results.addWidget(self._plan_row(
            name="Annuitätenkredit", total_cents=principal,
            monthly_cents=res.monthly_payment_cents, term_months=res.term_months,
            interest_rate=self.rate.value(), category="Divers"))
        plan_title = QLabel("Tilgungsplan")
        plan_title.setObjectName("H2")
        self.results.addWidget(plan_title)
        self.results.addWidget(_schedule_table(res.schedule), 1)


# --- Balloon tab -----------------------------------------------------------
class _BalloonTab(_CalcTab):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.loan = MoneyLineEdit(3000000)
        self.down = MoneyLineEdit(0)
        self.rate = _percent_field(4.9)
        self.term = _int_field(1, 600, 48, " Mon.")
        self.balloon = MoneyLineEdit(1000000)
        self.balloon_mode = QComboBox()
        self.balloon_mode.addItem("Betrag (€)", "eur")
        self.balloon_mode.addItem("% vom Kaufpreis", "pct")
        self.balloon_mode.currentIndexChanged.connect(self._on_balloon_mode)
        for i, w in enumerate([
            labelled("Finanzierungsbetrag", self.loan),
            labelled("Anzahlung", self.down),
            labelled("Zinssatz p.a.", self.rate),
            labelled("Laufzeit", self.term),
            labelled("Schlussrate", self.balloon),
            labelled("Schlussrate als", self.balloon_mode),
        ]):
            self.form.insertWidget(i, w)
        go = QPushButton("Berechnen")
        go.setObjectName("Primary")
        go.clicked.connect(self._compute)
        self.form.insertWidget(6, go)
        self.form.addStretch(1)
        self._compute()

    def _on_balloon_mode(self) -> None:
        """Reset the balloon field when the unit changes (€ vs %)."""
        if self.balloon_mode.currentData() == "pct":
            self.balloon.setText("30")
            self.balloon.setPlaceholderText("z. B. 30")
        else:
            self.balloon.set_cents(1000000)
            self.balloon.setPlaceholderText("0,00")

    def _compute(self) -> None:
        self.error.hide()
        loan = self.loan.cents()
        down = self.down.cents() or 0
        if loan is None:
            return self._show_error("Bitte einen gültigen Finanzierungsbetrag eingeben.")
        principal = loan - down
        if principal <= 0:
            return self._show_error("Die Anzahlung ist so hoch wie der Finanzierungsbetrag.")
        if self.balloon_mode.currentData() == "pct":
            raw = self.balloon.cents()  # field stores value*100 cents
            if raw is None:
                return self._show_error("Bitte einen gültigen Prozentwert eingeben.")
            pct_value = raw / 100  # back to the typed percent number
            if not 0 < pct_value <= 100:
                return self._show_error("Bitte einen Prozentwert zwischen 0 und 100 eingeben.")
            balloon_cents = min(round(loan * pct_value / 100), principal)
        else:
            balloon_cents = self.balloon.cents()
            if balloon_cents is None:
                return self._show_error("Bitte eine gültige Schlussrate eingeben.")
        try:
            cmp = balloon.compare(principal, balloon_cents, self.rate.value(), self.term.value())
        except ValueError as exc:
            return self._show_error(str(exc))

        bal = cmp.balloon
        c = self.ctx.colors
        clear_layout(self.results)
        self.results.addWidget(self._metric_row([
            ("Monatsrate", format_eur(bal.monthly_payment_cents), c["primary"]),
            ("Schlussrate", format_eur(bal.balloon_cents), c["amber"]),
            ("Empf. Rücklage/Mon.", format_eur(bal.recommended_reserve_cents), c["blue"]),
            ("Eff. Belastung/Mon.", format_eur(bal.effective_monthly_cents), c["text"]),
        ]))
        self.results.addWidget(self._plan_row(
            name="Ballonkredit", total_cents=principal,
            monthly_cents=bal.monthly_payment_cents, term_months=self.term.value(),
            interest_rate=self.rate.value(), category="Divers"))

        # Direct comparison standard vs balloon.
        cmp_title = QLabel("Vergleich: Standard vs. Ballon")
        cmp_title.setObjectName("H2")
        self.results.addWidget(cmp_title)
        self.results.addWidget(self._comparison_table(cmp, c))

        hint = QLabel(
            "ℹ️  Die Schlussrate wird am Ende der Laufzeit auf einen Schlag fällig. "
            "Lege monatlich die empfohlene Rücklage zurück, um sie sicher bezahlen zu können.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"background: {c['amber_soft']}; border-radius: 8px; padding: 12px;")
        self.results.addWidget(hint)
        self.results.addStretch(1)

    def _comparison_table(self, cmp, c) -> QTableWidget:
        rows = [
            ("Monatsrate", cmp.standard.monthly_payment_cents, cmp.balloon.monthly_payment_cents),
            ("Gesamtrückzahlung", cmp.total_standard_cents, cmp.total_balloon_cents),
            ("Gesamtzinsen", cmp.standard.total_interest_cents, cmp.balloon.total_interest_cents),
        ]
        table = QTableWidget(len(rows) + 2, 3)
        table.setHorizontalHeaderLabels(["", "Standard", "Ballon"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(34)
        for r, (label, std, bal) in enumerate(rows):
            table.setItem(r, 0, self._ro(label))
            table.setItem(r, 1, self._ro(format_eur(std), True))
            table.setItem(r, 2, self._ro(format_eur(bal), True))
        table.setItem(3, 0, self._ro("Zinsmehrkosten (Ballon)"))
        table.setItem(3, 1, self._ro(""))
        table.setItem(3, 2, self._ro(format_eur(cmp.extra_interest_cents), True))
        table.setItem(4, 0, self._ro("Monatliche Ersparnis (Ballon)"))
        table.setItem(4, 1, self._ro(""))
        table.setItem(4, 2, self._ro(format_eur(cmp.monthly_saving_cents), True))
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        align_table_headers(table, right_cols=(1, 2))
        table.setMaximumHeight(220)
        return table

    @staticmethod
    def _ro(text: str, right: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item


# --- Car tab ---------------------------------------------------------------
def _amount_row(label_text: str, field: QWidget) -> QWidget:
    """Compact 'label : field' row for an editable running-cost amount."""
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lab = QLabel(label_text)
    lab.setObjectName("FieldLabel")
    lab.setMinimumWidth(150)
    h.addWidget(lab)
    h.addWidget(field, 1)
    return row


class _AutoTab(_CalcTab):
    # Default monthly running-cost reserves (cents). Vollkasko scales with price.
    _DEF_KFZ = auto.KFZ_STEUER_COMBUSTION_CENTS   # ~15 €
    _DEF_TUV = auto.TUV_RESERVE_CENTS             # ~8 €
    _DEF_WARTUNG = 3000                           # 30 € (split from the old
    _DEF_REIFEN = 2000                            # 20 €  "Wartung & Reifen ~50 €")

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.price = MoneyLineEdit(3500000)
        self.down = MoneyLineEdit(500000)
        self.rate = _percent_field(4.9)
        self.term = _int_field(1, 600, 60, " Mon.")

        self.mode_standard = QRadioButton("Standard")
        self.mode_balloon = QRadioButton("Ballon")
        self.mode_standard.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_standard)
        mode_group.addButton(self.mode_balloon)
        mode_row = QWidget()
        ml = QHBoxLayout(mode_row)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.mode_standard)
        ml.addWidget(self.mode_balloon)
        ml.addStretch(1)

        self.balloon = MoneyLineEdit(1200000)
        self.electric = QCheckBox("Elektroauto (keine Kfz-Steuer)")

        # Editable monthly running costs (€/Monat). Vollkasko is pre-filled from
        # ~0.4 % of the price and keeps tracking the price until the user edits it.
        self.vk = MoneyLineEdit(round(3500000 * auto.VOLLKASKO_MONTHLY_RATE))
        self.kfz = MoneyLineEdit(self._DEF_KFZ)
        self.tuv = MoneyLineEdit(self._DEF_TUV)
        self.wartung = MoneyLineEdit(self._DEF_WARTUNG)
        self.reifen = MoneyLineEdit(self._DEF_REIFEN)
        self._vk_edited = False
        self.vk.textEdited.connect(lambda: setattr(self, "_vk_edited", True))
        self.electric.toggled.connect(
            lambda on: self.kfz.set_cents(0 if on else self._DEF_KFZ))

        widgets = [
            labelled("Kaufpreis", self.price),
            labelled("Anzahlung", self.down),
            labelled("Zinssatz p.a.", self.rate),
            labelled("Laufzeit", self.term),
            labelled("Finanzierungsart", mode_row),
            labelled("Schlussrate (nur Ballon)", self.balloon),
        ]
        for i, w in enumerate(widgets):
            self.form.insertWidget(i, w)

        extras_title = QLabel("Laufende Nebenkosten (€/Monat) – anpassbar")
        extras_title.setObjectName("FieldLabel")
        self.form.insertWidget(6, extras_title)
        self.form.insertWidget(7, self.electric)
        extra_rows = [
            ("Vollkasko", self.vk),
            ("Kfz-Steuer", self.kfz),
            ("TÜV-Rücklage", self.tuv),
            ("Wartung", self.wartung),
            ("Reifen-Rücklage", self.reifen),
        ]
        for i, (lab, field) in enumerate(extra_rows):
            self.form.insertWidget(8 + i, _amount_row(lab, field))

        go = QPushButton("Berechnen")
        go.setObjectName("Primary")
        go.clicked.connect(self._compute)
        self.form.insertWidget(13, go)
        self.form.addStretch(1)
        self._compute()

    def _compute(self) -> None:
        self.error.hide()
        price = self.price.cents()
        down = self.down.cents() or 0
        if price is None:
            return self._show_error("Bitte einen gültigen Kaufpreis eingeben.")
        # Keep the Vollkasko default in step with the price until manually changed.
        if not self._vk_edited:
            self.vk.set_cents(round(price * auto.VOLLKASKO_MONTHLY_RATE))
        balloon_cents = self.balloon.cents() or 0
        mode = "balloon" if self.mode_balloon.isChecked() else "standard"

        # User-edited running-cost amounts (0 / empty = not counted).
        override = {
            "Vollkasko": self.vk.cents() or 0,
            "Kfz-Steuer": self.kfz.cents() or 0,
            "TÜV-Rücklage": self.tuv.cents() or 0,
            "Wartung": self.wartung.cents() or 0,
            "Reifen-Rücklage": self.reifen.cents() or 0,
        }

        # Budget basis: the RECURRING monthly surplus (not after_all, which a
        # one-off credit this month would inflate), plus any current car fixed
        # costs that free up when the car is replaced. A car is a multi-year
        # commitment, so it must be judged against durable income only.
        disposable = self.ctx.overview().recurring_after_all_cents
        current_auto = sum(
            c.amount_cents for c in self.ctx.fixed.list() if c.category == "Auto")
        try:
            res = auto.compute(
                price_cents=price, down_payment_cents=down, annual_rate_pct=self.rate.value(),
                term_months=self.term.value(), mode=mode,
                balloon_cents=min(balloon_cents, price - down),
                extras_override=override,
                monthly_disposable_cents=disposable, current_auto_fixed_cents=current_auto)
        except ValueError as exc:
            return self._show_error(str(exc))

        c = self.ctx.colors
        badge_color = {"gut": c["green"], "knapp": c["amber"], "riskant": c["red"]}[res.feasibility]
        clear_layout(self.results)

        # Feasibility badge banner.
        badge = QLabel(f"  {res.feasibility_label}  ")
        badge.setStyleSheet(
            f"color: {theme.on_color(badge_color)}; background: {badge_color}; "
            f"border-radius: 9px; padding: 8px 14px; font-weight: 700; font-size: 15px;")
        badge_row = QHBoxLayout()
        badge_row.addWidget(badge)
        badge_row.addStretch(1)
        badge_wrap = QWidget()
        badge_wrap.setLayout(badge_row)
        self.results.addWidget(badge_wrap)

        self.results.addWidget(self._metric_row([
            ("Finanzierungsrate", format_eur(res.monthly_financing_cents), c["primary"]),
            ("Nebenkosten/Mon.", format_eur(res.extras_total_cents), c["amber"]),
            ("Gesamt/Monat", format_eur(res.monthly_total_cents), c["text"]),
        ]))
        rem = res.remaining_after_auto_cents
        self.results.addWidget(self._metric_row([
            ("Verfügbar (Verbleibend)", format_eur(disposable), c["blue"]),
            ("Verbleibend mit diesem Auto", format_eur(rem),
             c["green"] if rem >= 0 else c["red"]),
        ]))
        # Plan the financing instalment (not the running costs) as a car loan.
        self.results.addWidget(self._plan_row(
            name="Autokredit", total_cents=max(0, price - down),
            monthly_cents=res.monthly_financing_cents, term_months=self.term.value(),
            interest_rate=self.rate.value(), category="Auto"))

        # Make the budget basis transparent (esp. the freed existing car costs).
        if current_auto > 0:
            note = QLabel(
                f"Budget = Verbleibend {format_eur(disposable)} + frei werdende "
                f"Autokosten {format_eur(current_auto)} = {format_eur(res.available_budget_cents)} "
                f"– Gesamt/Monat {format_eur(res.monthly_total_cents)}.")
            note.setObjectName("Muted")
            note.setWordWrap(True)
            self.results.addWidget(note)

        if res.extras_breakdown:
            title = QLabel("Nebenkosten im Detail")
            title.setObjectName("H2")
            self.results.addWidget(title)
            hint = QLabel("Beträge links anpassen (z. B. mehr Reifen-Rücklage), dann neu berechnen.")
            hint.setObjectName("Faint")
            hint.setWordWrap(True)
            self.results.addWidget(hint)
            for label, cents in res.extras_breakdown.items():
                line = QHBoxLayout()
                line.addWidget(QLabel(label))
                line.addStretch(1)
                val = QLabel(format_eur(cents))
                val.setStyleSheet("font-weight: 600;")
                line.addWidget(val)
                holder = QWidget()
                holder.setLayout(line)
                self.results.addWidget(holder)
        self.results.addStretch(1)


# --- House tab -------------------------------------------------------------
class _HausTab(_CalcTab):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.price = MoneyLineEdit(35000000)
        self.equity = MoneyLineEdit(7000000)
        self.rate = _percent_field(3.6)
        self.fixed_period = _int_field(1, 40, 10, " Jahre")
        self.term = _int_field(1, 50, 30, " Jahre")
        widgets = [
            labelled("Kaufpreis", self.price),
            labelled("Eigenkapital", self.equity),
            labelled("Sollzins p.a.", self.rate),
            labelled("Sollzinsbindung", self.fixed_period),
            labelled("Laufzeit (Tilgung)", self.term),
        ]
        for i, w in enumerate(widgets):
            self.form.insertWidget(i, w)
        go = QPushButton("Berechnen")
        go.setObjectName("Primary")
        go.clicked.connect(self._compute)
        self.form.insertWidget(5, go)
        self.form.addStretch(1)
        self._compute()

    def _compute(self) -> None:
        self.error.hide()
        price = self.price.cents()
        equity = self.equity.cents() or 0
        if price is None:
            return self._show_error("Bitte einen gültigen Kaufpreis eingeben.")
        try:
            res = house.compute(
                price_cents=price, equity_cents=equity, annual_rate_pct=self.rate.value(),
                fixed_period_years=self.fixed_period.value(), term_years=self.term.value())
        except ValueError as exc:
            return self._show_error(str(exc))

        c = self.ctx.colors
        clear_layout(self.results)
        self.results.addWidget(self._metric_row([
            ("Darlehen", format_eur(res.loan_cents), c["text"]),
            ("Monatsrate", format_eur(res.monthly_payment_cents), c["primary"]),
        ]))
        self.results.addWidget(self._metric_row([
            ("Restschuld nach Zinsbindung", format_eur(res.residual_after_fixed_cents), c["amber"]),
            ("Gesamtzinsen", format_eur(res.total_interest_cents), c["red"]),
        ]))
        self.results.addWidget(self._plan_row(
            name="Hausdarlehen", total_cents=res.loan_cents,
            monthly_cents=res.monthly_payment_cents, term_months=self.term.value() * 12,
            interest_rate=self.rate.value(), category="Haus"))
        plan_title = QLabel("Tilgungsplan")
        plan_title.setObjectName("H2")
        self.results.addWidget(plan_title)
        self.results.addWidget(_schedule_table(res.schedule), 1)


class RechnerView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(6)
        layout.addWidget(heading("Rechner"))
        layout.addWidget(muted("Finanzierungen durchrechnen – mit vollständigem Tilgungsplan."))

        self.tabs = QTabWidget()
        self.tabs.addTab(_AnnuityTab(ctx), "Annuität")
        self.tabs.addTab(_BalloonTab(ctx), "Ballonkredit")
        self.tabs.addTab(_AutoTab(ctx), "Auto-Finanzierung")
        self.tabs.addTab(_HausTab(ctx), "Haus-Finanzierung")
        layout.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        pass

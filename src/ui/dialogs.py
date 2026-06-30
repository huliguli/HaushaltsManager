"""Modal add/edit dialogs for income, fixed costs, expenses and credits.

Each dialog builds and validates a model dataclass. Validation errors are shown
inline (never as a raw exception), and money/date fields use the German-aware
parsers so the user can type "1.234,56" or leave optional dates blank.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from modules import dates
from modules.models import (
    CREDIT_CATEGORIES,
    CREDIT_STATUS,
    CREDIT_STATUS_LABELS,
    EXPENSE_CATEGORIES,
    FIXED_CATEGORIES,
    INCOME_TYPE_LABELS,
    INCOME_TYPES,
    Credit,
    FixedCost,
    IncomeSource,
    VariableExpense,
)
from modules.money import try_parse_eur
from ui.widgets.inputs import MoneyLineEdit, labelled


def _opt_date(text: str) -> str | None:
    """Parse an optional date field. Empty -> None; invalid -> ValueError."""
    text = (text or "").strip()
    if not text:
        return None
    d = dates.parse_date(text)
    if d is None:
        raise ValueError(f"„{text}“ ist kein gültiges Datum (TT.MM.JJJJ).")
    return dates.to_iso(d)


class _BaseDialog(QDialog):
    """Shared scaffold: titled form grid, inline error label, OK/Cancel."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        # Wide enough that the longest expense category ("Essen Bestellen &
        # Fast Food") shows fully in the two-column form's category combo.
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(16)

        header = QLabel(title)
        header.setObjectName("H2")
        root.addWidget(header)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(12)
        root.addLayout(self.grid)

        self._error = QLabel("")
        self._error.setStyleSheet("color: #d6453d; font-size: 12px;")
        self._error.setWordWrap(True)
        self._error.hide()
        root.addWidget(self._error)

        root.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Speichern")
        save.setObjectName("Primary")
        save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self._row = 0

    def add_row(self, left: QWidget, right: QWidget | None = None) -> None:
        if right is None:
            self.grid.addWidget(left, self._row, 0, 1, 2)
        else:
            self.grid.addWidget(left, self._row, 0)
            self.grid.addWidget(right, self._row, 1)
        self._row += 1

    def show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _on_save(self) -> None:
        try:
            self.build()  # subclass validates + stores self.result_model
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.accept()

    def build(self) -> None:  # noqa: D401 - overridden
        raise NotImplementedError


# --- Income ----------------------------------------------------------------
class IncomeDialog(_BaseDialog):
    def __init__(self, item: IncomeSource | None = None, parent=None) -> None:
        super().__init__("Einnahme bearbeiten" if item else "Einnahme hinzufügen", parent)
        self._id = item.id if item else None

        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText("z. B. Teilzeit")
        self.amount = MoneyLineEdit(item.amount_cents if item else None)
        self.kind = QComboBox()
        for key in INCOME_TYPES:
            self.kind.addItem(INCOME_TYPE_LABELS[key], key)
        if item:
            self.kind.setCurrentIndex(INCOME_TYPES.index(item.income_type)
                                      if item.income_type in INCOME_TYPES else 3)
        self.note = QLineEdit(item.note if item else "")
        self.active = QCheckBox("Aktiv (zählt zur Monatssumme)")
        self.active.setChecked(item.active if item else True)

        self.add_row(labelled("Bezeichnung", self.name), labelled("Betrag pro Monat", self.amount))
        self.add_row(labelled("Art", self.kind), labelled("Notiz (optional)", self.note))
        self.add_row(self.active)

    def build(self) -> None:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bitte eine Bezeichnung eingeben.")
        amount = self.amount.cents()
        if amount is None:
            raise ValueError("Bitte einen gültigen Betrag eingeben.")
        self.result_model = IncomeSource(
            id=self._id, name=name, amount_cents=amount,
            income_type=self.kind.currentData(), active=self.active.isChecked(),
            note=self.note.text().strip(),
        )


# --- Fixed cost ------------------------------------------------------------
class FixedCostDialog(_BaseDialog):
    def __init__(self, item: FixedCost | None = None, parent=None) -> None:
        super().__init__("Fixkosten bearbeiten" if item else "Fixkosten hinzufügen", parent)
        self._id = item.id if item else None

        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText("z. B. Miete")
        self.amount = MoneyLineEdit(item.amount_cents if item else None)
        self.category = QComboBox()
        self.category.addItems(FIXED_CATEGORIES)
        if item and item.category in FIXED_CATEGORIES:
            self.category.setCurrentText(item.category)
        self.start = QLineEdit(dates.format_date(item.start_date) if item and item.start_date else "")
        self.start.setPlaceholderText("optional · TT.MM.JJJJ")
        self.end = QLineEdit(dates.format_date(item.end_date) if item and item.end_date else "")
        self.end.setPlaceholderText("unbegrenzt · TT.MM.JJJJ")
        self.note = QLineEdit(item.note if item else "")
        self.active = QCheckBox("Aktiv")
        self.active.setChecked(item.active if item else True)

        self.add_row(labelled("Bezeichnung", self.name), labelled("Betrag pro Monat", self.amount))
        self.add_row(labelled("Kategorie", self.category), labelled("Notiz (optional)", self.note))
        self.add_row(labelled("Beginn (optional)", self.start),
                     labelled("Ende (leer = unbegrenzt)", self.end))
        self.add_row(self.active)

    def build(self) -> None:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bitte eine Bezeichnung eingeben.")
        amount = self.amount.cents()
        if amount is None:
            raise ValueError("Bitte einen gültigen Betrag eingeben.")
        start = _opt_date(self.start.text())
        end = _opt_date(self.end.text())
        if start and end and end < start:
            raise ValueError("Das Enddatum liegt vor dem Beginn.")
        self.result_model = FixedCost(
            id=self._id, name=name, amount_cents=amount,
            category=self.category.currentText(), start_date=start, end_date=end,
            note=self.note.text().strip(), active=self.active.isChecked(),
        )


# --- Variable expense ------------------------------------------------------
class ExpenseDialog(_BaseDialog):
    def __init__(self, item: VariableExpense | None = None, parent=None) -> None:
        super().__init__("Ausgabe bearbeiten" if item else "Ausgabe hinzufügen", parent)
        self._id = item.id if item else None

        default_date = dates.format_date(item.date) if item else dates.format_date(dates.today())
        self.date = QLineEdit(default_date)
        self.date.setPlaceholderText("TT.MM.JJJJ")
        self.amount = MoneyLineEdit(item.amount_cents if item else None)
        self.category = QComboBox()
        self.category.addItems(EXPENSE_CATEGORIES)
        if item and item.category in EXPENSE_CATEGORIES:
            self.category.setCurrentText(item.category)
        self.description = QLineEdit(item.description if item else "")

        self.receipt = QLineEdit(item.receipt_path if item and item.receipt_path else "")
        self.receipt.setPlaceholderText("optional · Pfad zum Belegfoto")
        browse = QPushButton("Durchsuchen…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse_receipt)
        receipt_row = QWidget()
        rl = QHBoxLayout(receipt_row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.receipt, 1)
        rl.addWidget(browse)

        self.recurring = QCheckBox("Monatlich wiederkehrend (erscheint automatisch in jedem Folgemonat)")
        self.recurring.setChecked(item.recurring if item else False)

        self.add_row(labelled("Datum (bei wiederkehrend: ab diesem Monat)", self.date),
                     labelled("Betrag", self.amount))
        self.add_row(labelled("Kategorie", self.category),
                     labelled("Beschreibung", self.description))
        self.add_row(labelled("Beleg (optional)", receipt_row))
        self.add_row(self.recurring)

    def _browse_receipt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Belegfoto wählen", "",
            "Bilder (*.png *.jpg *.jpeg *.webp);;Alle Dateien (*.*)",
        )
        if path:
            self.receipt.setText(path)

    def build(self) -> None:
        d = dates.parse_date(self.date.text())
        if d is None:
            raise ValueError("Bitte ein gültiges Datum (TT.MM.JJJJ) eingeben.")
        amount = self.amount.cents()
        if amount is None:
            raise ValueError("Bitte einen gültigen Betrag eingeben.")
        self.result_model = VariableExpense(
            id=self._id, date=dates.to_iso(d), amount_cents=amount,
            category=self.category.currentText(),
            description=self.description.text().strip(),
            receipt_path=self.receipt.text().strip() or None,
            recurring=self.recurring.isChecked(),
        )


# --- Credit ----------------------------------------------------------------
class CreditDialog(_BaseDialog):
    """Add/edit a credit. The user may supply only some figures; the missing
    ones are derived linearly (without interest) so a record is always complete
    enough to display — the Rechner tab handles interest-accurate maths."""

    def __init__(self, item: Credit | None = None, fixed_costs: list | None = None,
                 parent=None) -> None:
        super().__init__("Kredit bearbeiten" if item else "Kredit hinzufügen", parent)
        self._id = item.id if item else None

        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText("z. B. Autokredit")
        self.total = MoneyLineEdit(item.total_cents if item and item.total_cents else None)
        self.monthly = MoneyLineEdit(item.monthly_cents if item and item.monthly_cents else None)
        self.term = QLineEdit(str(item.term_months) if item and item.term_months else "")
        self.term.setPlaceholderText("Monate")
        self.rate = QLineEdit(str(item.interest_rate) if item and item.interest_rate else "")
        self.rate.setPlaceholderText("% p.a. · optional")
        self.start = QLineEdit(dates.format_date(item.start_date) if item and item.start_date else "")
        self.start.setPlaceholderText("optional")
        self.end = QLineEdit(dates.format_date(item.end_date) if item and item.end_date else "")
        self.end.setPlaceholderText("optional")
        self.category = QComboBox()
        self.category.addItems(CREDIT_CATEGORIES)
        if item and item.category in CREDIT_CATEGORIES:
            self.category.setCurrentText(item.category)
        self.status = QComboBox()
        for key in CREDIT_STATUS:
            self.status.addItem(CREDIT_STATUS_LABELS[key], key)
        if item:
            self.status.setCurrentIndex(CREDIT_STATUS.index(item.status)
                                        if item.status in CREDIT_STATUS else 0)
        self.note = QLineEdit(item.note if item else "")

        self.link = QComboBox()
        self.link.addItem("— keine Verknüpfung —", None)
        for fc in (fixed_costs or []):
            self.link.addItem(f"{fc.name}", fc.id)
        if item and item.linked_fixed_cost_id is not None:
            idx = self.link.findData(item.linked_fixed_cost_id)
            if idx >= 0:
                self.link.setCurrentIndex(idx)

        self.add_row(labelled("Bezeichnung", self.name), labelled("Kategorie", self.category))
        self.add_row(labelled("Gesamtbetrag (oder Rate)", self.total),
                     labelled("Monatsrate (oder Gesamt)", self.monthly))
        self.add_row(labelled("Restlaufzeit", self.term),
                     labelled("Zinssatz (optional)", self.rate))
        self.add_row(labelled("Beginn (optional)", self.start),
                     labelled("Ende (optional)", self.end))
        self.add_row(labelled("Status", self.status),
                     labelled("Verknüpfte Fixkosten", self.link))
        self.add_row(labelled("Notiz (optional)", self.note))

    def build(self) -> None:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bitte eine Bezeichnung eingeben.")
        total = self.total.cents()
        monthly = self.monthly.cents()
        term = self._opt_int(self.term.text(), "Restlaufzeit")
        rate = self._opt_float(self.rate.text(), "Zinssatz")
        start = _opt_date(self.start.text())
        end = _opt_date(self.end.text())

        if total is None and monthly is None:
            raise ValueError("Bitte Gesamtbetrag oder Monatsrate angeben.")

        # Derive term from the date range if not given.
        if term is None and start and end:
            sd, ed = dates.parse_date(start), dates.parse_date(end)
            term = max(1, dates.months_between(sd, ed))

        # Fill in the missing of {total, monthly} linearly when a term exists.
        if term:
            if monthly is None and total is not None:
                monthly = round(total / term)
            elif total is None and monthly is not None:
                total = monthly * term
            if end is None and start is not None:
                ed = dates.add_months(dates.parse_date(start), term)
                end = dates.to_iso(ed)

        self.result_model = Credit(
            id=self._id, name=name, total_cents=total, monthly_cents=monthly,
            start_date=start, end_date=end, term_months=term, interest_rate=rate,
            category=self.category.currentText(), note=self.note.text().strip(),
            status=self.status.currentData(), linked_fixed_cost_id=self.link.currentData(),
        )

    @staticmethod
    def _opt_int(text: str, label: str) -> int | None:
        text = (text or "").strip()
        if not text:
            return None
        try:
            value = int(float(text.replace(",", ".")))
        except ValueError as exc:
            raise ValueError(f"{label}: bitte eine ganze Zahl eingeben.") from exc
        if value <= 0:
            raise ValueError(f"{label} muss größer als 0 sein.")
        return value

    @staticmethod
    def _opt_float(text: str, label: str) -> float | None:
        text = (text or "").strip().replace("%", "").replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(f"{label}: bitte eine Zahl eingeben.") from exc

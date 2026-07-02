"""Dialogs for the import flows: Excel column mapping and PDF amount picking."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules import dates
from modules.models import EXPENSE_CATEGORIES, VariableExpense
from modules.money import format_eur
from ui.widgets.inputs import labelled


class MappingDialog(QDialog):
    """Let the user confirm/adjust which column is date/amount/description."""

    _FIELDS = [("amount", "Betrag *"), ("date", "Datum"),
               ("description", "Beschreibung"), ("category", "Kategorie")]

    def __init__(self, headers: list[str], data_rows: list[list], guess: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Excel-Import – Spalten zuordnen")
        self.setModal(True)
        self.setMinimumSize(720, 520)
        self._headers = headers
        self._data = data_rows

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)
        title = QLabel("Spalten zuordnen")
        title.setObjectName("H2")
        root.addWidget(title)
        root.addWidget(QLabel("Ordne die erkannten Spalten den Feldern zu. „Betrag“ ist erforderlich."))

        self._combos: dict[str, QComboBox] = {}
        field_row = QHBoxLayout()
        for key, label in self._FIELDS:
            combo = QComboBox()
            combo.addItem("— keine —", None)
            for i, h in enumerate(headers):
                combo.addItem(f"{i + 1}: {h or '(leer)'}", i)
            if guess.get(key) is not None:
                idx = combo.findData(guess[key])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._combos[key] = combo
            field_row.addWidget(labelled(label, combo))
        root.addLayout(field_row)

        cat_row = QHBoxLayout()
        self.default_cat = QComboBox()
        self.default_cat.addItems(EXPENSE_CATEGORIES)
        cat_row.addWidget(labelled("Standard-Kategorie (falls keine Spalte)", self.default_cat))
        cat_row.addStretch(1)
        root.addLayout(cat_row)

        preview = QTableWidget(min(len(data_rows), 8), len(headers))
        preview.setHorizontalHeaderLabels([str(h) for h in headers])
        preview.verticalHeader().setVisible(False)
        preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for r in range(min(len(data_rows), 8)):
            for c in range(len(headers)):
                val = data_rows[r][c] if c < len(data_rows[r]) else ""
                preview.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
        preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(QLabel("Vorschau:"))
        root.addWidget(preview, 1)

        self._error = QLabel("")
        self._error.setObjectName("ErrorText")
        self._error.hide()
        root.addWidget(self._error)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Importieren")
        ok.setObjectName("Primary")
        ok.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)

    def _accept(self) -> None:
        if self._combos["amount"].currentData() is None:
            self._error.setText("Bitte eine Spalte für „Betrag“ wählen.")
            self._error.show()
            return
        self.accept()

    def mapping(self) -> dict:
        return {k: c.currentData() for k, c in self._combos.items()}

    def default_category(self) -> str:
        return self.default_cat.currentText()


class PdfImportDialog(QDialog):
    """Pick which extracted amounts to import as expenses (correctable)."""

    def __init__(self, amounts: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF-Import – Beträge übernehmen")
        self.setModal(True)
        self.setMinimumSize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        title = QLabel("Erkannte Beträge")
        title.setObjectName("H2")
        root.addWidget(title)
        root.addWidget(QLabel("Wähle die zu übernehmenden Beträge, prüfe Datum und Kategorie."))

        top = QHBoxLayout()
        self.date = QLineEdit(dates.format_date(dates.today()))
        top.addWidget(labelled("Datum für alle", self.date))
        self.global_cat = QComboBox()
        self.global_cat.addItems(EXPENSE_CATEGORIES)
        top.addWidget(labelled("Kategorie für alle", self.global_cat))
        top.addStretch(1)
        apply_cat = QPushButton("Auf alle anwenden")
        apply_cat.setObjectName("Ghost")
        apply_cat.clicked.connect(self._apply_global_category)
        top.addWidget(apply_cat)
        root.addLayout(top)

        self.table = QTableWidget(len(amounts), 4)
        self.table.setHorizontalHeaderLabels(["Übernehmen", "Betrag", "Kategorie", "Fundstelle"])
        self.table.verticalHeader().setVisible(False)
        self._checks: list[QCheckBox] = []
        self._cats: list[QComboBox] = []
        self._cents: list[int] = []
        for r, a in enumerate(amounts):
            chk = QCheckBox()
            chk.setChecked(False)
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(10, 0, 0, 0)
            hl.addWidget(chk)
            self.table.setCellWidget(r, 0, holder)
            self._checks.append(chk)

            amt = QTableWidgetItem(format_eur(a["cents"]))
            amt.setFlags(amt.flags() & ~Qt.ItemFlag.ItemIsEditable)
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 1, amt)
            self._cents.append(a["cents"])

            cat = QComboBox()
            cat.addItems(EXPENSE_CATEGORIES)
            self.table.setCellWidget(r, 2, cat)
            self._cats.append(cat)

            ctx = QTableWidgetItem(a["line"])
            ctx.setFlags(ctx.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 3, ctx)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Ausgewählte übernehmen")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)

    def _apply_global_category(self) -> None:
        target = self.global_cat.currentText()
        for combo in self._cats:
            combo.setCurrentText(target)

    def selected_expenses(self) -> list[VariableExpense]:
        d = dates.parse_date(self.date.text()) or dates.today()
        iso = dates.to_iso(d)
        out = []
        for i, chk in enumerate(self._checks):
            if chk.isChecked():
                out.append(VariableExpense(
                    date=iso, amount_cents=abs(self._cents[i]),
                    category=self._cats[i].currentText(), description="PDF-Import"))
        return out

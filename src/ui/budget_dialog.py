"""Dialog to set optional monthly spending targets per expense category.

One money field per category (pre-filled from the stored budgets); saving writes
every non-empty value and clears the ones left blank. Amounts stay integer cents
throughout (via MoneyLineEdit). Purely additive data — leaving everything blank
simply means "no budgets".
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from modules.models import EXPENSE_CATEGORIES
from ui.widgets.inputs import MoneyLineEdit


class CategoryBudgetDialog(QDialog):
    """Edit monthly limits for every expense category in one place."""

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Budgets festlegen")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMinimumHeight(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        header = QLabel("Monatsbudgets")
        header.setObjectName("H2")
        root.addWidget(header)
        sub = QLabel("Lege optional pro Kategorie ein Monatslimit fest. Leer lassen = kein Budget.")
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Scrollable list of category rows.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(2, 4, 2, 4)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        current = self.ctx.budgets.all()
        self._fields: dict[str, MoneyLineEdit] = {}
        for i, cat in enumerate(EXPENSE_CATEGORIES):
            label = QLabel(cat)
            field = MoneyLineEdit(current.get(cat), placeholder="kein Limit")
            field.setAccessibleName(f"Monatsbudget {cat}")
            field.setFixedWidth(150)
            self._fields[cat] = field
            grid.addWidget(label, i, 0)
            grid.addWidget(field, i, 1, alignment=Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(0, 1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Speichern")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def _on_save(self) -> None:
        for cat, field in self._fields.items():
            self.ctx.budgets.set(cat, field.cents() or 0)
        self.accept()

"""Dialogs for savings goals: add/edit one goal, and manage the list.

The add/edit dialog builds a validated :class:`SavingsGoal`; the manage dialog
is the one place to see, create, edit and delete every goal (opened from the
dashboard card). Money fields use the German-aware parser, the start month
accepts ``MM.JJJJ`` or a full date — consistent with the other dialogs.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from modules import dates, savings_goals
from modules.models import SavingsGoal
from modules.money import format_eur
from ui.dialogs import _BaseDialog, _opt_date
from ui.widgets.common import align_table_headers, table_shortcuts
from ui.widgets.inputs import MoneyLineEdit, labelled

_ROLE_ID = Qt.ItemDataRole.UserRole


class SavingsGoalDialog(_BaseDialog):
    """Add or edit a single savings goal."""

    def __init__(self, item: SavingsGoal | None = None, parent=None) -> None:
        super().__init__("Sparziel bearbeiten" if item and item.id else "Sparziel anlegen",
                         parent)
        self._id = item.id if item else None

        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText("z. B. Urlaub 2027")
        self.target = MoneyLineEdit(item.target_cents if item else None)
        self.monthly = MoneyLineEdit(item.monthly_cents if item else None)
        start = item.start_date if item and item.start_date else dates.to_iso(dates.today())
        self.start = QLineEdit(dates.format_date(start))
        self.start.setPlaceholderText("TT.MM.JJJJ oder MM.JJJJ")
        self.manual = MoneyLineEdit(
            item.manual_cents if item and item.manual_cents else None,
            placeholder="0,00")
        self.note = QLineEdit(item.note if item else "")

        self.add_row(labelled("Bezeichnung", self.name),
                     labelled("Zielbetrag", self.target))
        self.add_row(labelled("Sparrate / Monat", self.monthly),
                     labelled("Start (zählt ab diesem Monat)", self.start))
        self.add_row(labelled("Startguthaben / Korrektur (optional)", self.manual,
                              hint="Wird zum berechneten Stand addiert – z. B. was "
                                   "schon auf dem Konto liegt."),
                     labelled("Notiz (optional)", self.note))

    def build(self) -> None:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bitte eine Bezeichnung eingeben.")
        target = self.target.cents()
        if target is None or target <= 0:
            raise ValueError("Bitte einen Zielbetrag größer als 0 eingeben.")
        monthly = self.monthly.cents()
        if monthly is None or monthly < 0:
            raise ValueError("Bitte eine gültige Sparrate eingeben (0 ist erlaubt).")
        start_iso = _opt_date(self.start.text()) or dates.to_iso(dates.today())
        self.result_model = SavingsGoal(
            id=self._id, name=name, target_cents=target, monthly_cents=monthly,
            start_date=start_iso, manual_cents=self.manual.cents() or 0,
            note=self.note.text().strip())


class SavingsGoalsManageDialog(QDialog):
    """List, add, edit and delete savings goals in one place."""

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.changed = False  # let the caller know whether to notify views
        self.setWindowTitle("Sparziele verwalten")
        self.setModal(True)
        self.setMinimumSize(700, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        header = QLabel("Sparziele")
        header.setObjectName("H2")
        root.addWidget(header)
        sub = QLabel("Der Stand wächst automatisch mit der Sparrate ab dem Startmonat "
                     "– über die Korrektur kannst du ihn jederzeit angleichen.")
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        root.addWidget(sub)

        bar = QHBoxLayout()
        bar.addStretch(1)
        edit = QPushButton("Bearbeiten")
        edit.setObjectName("Ghost")
        delete = QPushButton("Löschen")
        delete.setObjectName("Danger")
        add = QPushButton("+ Sparziel")
        add.setObjectName("Primary")
        bar.addWidget(edit)
        bar.addWidget(delete)
        bar.addWidget(add)
        root.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Bezeichnung", "Ziel", "Rate / Monat", "Stand", "Prognose"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.doubleClicked.connect(lambda: self._edit())
        table_shortcuts(self.table, self._edit, self._delete)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Schließen")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)
        self._reload()

    def _reload(self) -> None:
        goals = self.ctx.goals.list()
        self.table.setRowCount(len(goals))
        for r, g in enumerate(goals):
            p = savings_goals.compute(g)
            name = QTableWidgetItem(g.name)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name.setData(_ROLE_ID, g.id)
            self.table.setItem(r, 0, name)
            for col, text in ((1, format_eur(g.target_cents)),
                              (2, format_eur(g.monthly_cents)),
                              (3, f"{format_eur(p.saved_cents)} · {round(p.ratio * 100)} %")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, col, item)
            eta = QTableWidgetItem(savings_goals.eta_label(p))
            eta.setFlags(eta.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 4, eta)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        align_table_headers(self.table, right_cols=(1, 2, 3))

    def _selected(self) -> SavingsGoal | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        rid = item.data(_ROLE_ID) if item else None
        return self.ctx.goals.get(rid) if rid is not None else None

    def _add(self) -> None:
        dlg = SavingsGoalDialog(parent=self)
        if dlg.exec():
            self.ctx.goals.add(dlg.result_model)
            self.changed = True
            self._reload()

    def _edit(self) -> None:
        goal = self._selected()
        if goal is None:
            return
        dlg = SavingsGoalDialog(goal, parent=self)
        if dlg.exec():
            self.ctx.goals.update(dlg.result_model)
            self.changed = True
            self._reload()

    def _delete(self) -> None:
        goal = self._selected()
        if goal is None:
            return
        if QMessageBox.question(self, "Löschen",
                                f"Sparziel „{goal.name}“ wirklich löschen?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.ctx.goals.delete(goal.id)
        self.changed = True
        self._reload()

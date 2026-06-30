"""Haushaltsbuch: income, fixed costs and variable expenses.

Three tabs share the same pattern — a toolbar with a running total and add /
edit / delete actions over a table. Fixed costs add category/status filters and
traffic-light colouring; variable expenses add month navigation.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules import dates
from modules.models import (
    FIXED_CATEGORIES,
    INCOME_TYPE_LABELS,
)
from modules.money import format_eur
from ui import theme
from ui.dialogs import ExpenseDialog, FixedCostDialog, IncomeDialog
from ui.views.base_view import BaseView
from ui.widgets.common import (
    Pill,
    TablePanel,
    align_table_headers,
    heading,
    muted,
    pill_cell,
)

_ROLE_ID = Qt.ItemDataRole.UserRole


def _money_item(cents: int) -> QTableWidgetItem:
    item = QTableWidgetItem(format_eur(cents))
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _text_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.horizontalHeader().setHighlightSections(False)
    table.verticalHeader().setDefaultSectionSize(40)
    return table


def _toolbar(total_label: QLabel, add_text: str) -> tuple[QWidget, QPushButton, QPushButton, QPushButton]:
    bar = QWidget()
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(total_label)
    layout.addStretch(1)
    edit = QPushButton("Bearbeiten")
    edit.setObjectName("Ghost")
    delete = QPushButton("Löschen")
    delete.setObjectName("Danger")
    add = QPushButton(add_text)
    add.setObjectName("Primary")
    layout.addWidget(edit)
    layout.addWidget(delete)
    layout.addWidget(add)
    return bar, add, edit, delete


def _selected_id(table: QTableWidget) -> int | None:
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    return item.data(_ROLE_ID) if item else None


# --- Income tab ------------------------------------------------------------
class _IncomeTab(QWidget):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 14, 2, 2)
        layout.setSpacing(12)

        self.total = QLabel()
        self.total.setObjectName("H2")
        bar, add, edit, delete = _toolbar(self.total, "+ Einnahme")
        layout.addWidget(bar)

        self.table = _make_table(["Bezeichnung", "Art", "Betrag / Monat", "Status"])
        self.table.doubleClicked.connect(lambda: self._edit())
        self._panel = TablePanel(
            self.table, "Noch keine Einnahmen erfasst.",
            "Lege über „+ Einnahme“ deine erste Einnahmequelle an.")
        layout.addWidget(self._panel, 1)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)

    def refresh(self) -> None:
        colors = self.ctx.colors
        items = self.ctx.income.list()
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            name = _text_item(it.name)
            name.setData(_ROLE_ID, it.id)
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, _text_item(INCOME_TYPE_LABELS.get(it.income_type, "")))
            self.table.setItem(r, 2, _money_item(it.amount_cents))
            key = "green" if it.active else "grey"
            label = "Aktiv" if it.active else "Inaktiv"
            self.table.setCellWidget(r, 3, pill_cell(
                Pill(label, theme.ampel_color(key, colors), theme.ampel_soft(key, colors))))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # Status hosts a pill cell-widget -> fixed width so it never clips.
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 110)
        align_table_headers(self.table, right_cols=(2,))
        self._panel.update_state()
        self.total.setText(f"Aktive Einnahmen: {format_eur(self.ctx.income.total_active())}")

    def _add(self) -> None:
        dlg = IncomeDialog(parent=self)
        if dlg.exec():
            self.ctx.income.add(dlg.result_model)
            self.ctx.notify_changed()

    def _edit(self) -> None:
        rid = _selected_id(self.table)
        if rid is None:
            return
        item = self.ctx.income.get(rid)
        if not item:
            return
        dlg = IncomeDialog(item, parent=self)
        if dlg.exec():
            self.ctx.income.update(dlg.result_model)
            self.ctx.notify_changed()

    def _delete(self) -> None:
        rid = _selected_id(self.table)
        if rid is None:
            return
        if QMessageBox.question(self, "Löschen", "Diese Einnahme wirklich löschen?") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.income.delete(rid)
            self.ctx.notify_changed()


# --- Fixed costs tab -------------------------------------------------------
class _FixedTab(QWidget):
    _STATUS_FILTERS = [
        ("Alle", None), ("Bald (≤6 Mon.)", "green"), ("Mittel (6–24)", "amber"),
        ("Unbegrenzt", "grey"), ("Überfällig", "red"),
    ]

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 14, 2, 2)
        layout.setSpacing(12)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.cat_filter = QComboBox()
        self.cat_filter.addItem("Alle Kategorien", None)
        for c in FIXED_CATEGORIES:
            self.cat_filter.addItem(c, c)
        self.status_filter = QComboBox()
        for label, key in self._STATUS_FILTERS:
            self.status_filter.addItem(label, key)
        self.cat_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(QLabel("Filter:"))
        filters.addWidget(self.cat_filter)
        filters.addWidget(self.status_filter)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.total = QLabel()
        self.total.setObjectName("H2")
        bar, add, edit, delete = _toolbar(self.total, "+ Fixkosten")
        layout.addWidget(bar)

        self.table = _make_table(
            ["Bezeichnung", "Kategorie", "Betrag / Monat", "Ende", "Status"])
        self.table.doubleClicked.connect(lambda: self._edit())
        self._panel = TablePanel(
            self.table, "Keine Fixkosten in dieser Ansicht.",
            "Lege über „+ Fixkosten“ einen Eintrag an oder ändere den Filter.")
        layout.addWidget(self._panel, 1)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)

    def refresh(self) -> None:
        colors = self.ctx.colors
        cat = self.cat_filter.currentData()
        status = self.status_filter.currentData()
        items = self.ctx.fixed.list()
        rows = []
        for it in items:
            if cat and it.category != cat:
                continue
            if status and it.status_key() != status:
                continue
            rows.append(it)

        self.table.setRowCount(len(rows))
        shown_total = 0
        for r, it in enumerate(rows):
            shown_total += it.amount_cents
            name = _text_item(it.name)
            name.setData(_ROLE_ID, it.id)
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, _text_item(it.category))
            self.table.setItem(r, 2, _money_item(it.amount_cents))
            self.table.setItem(r, 3, _text_item(dates.format_date(it.end_date) or "unbegrenzt"))
            key = it.status_key()
            pill = Pill(dates.format_months_remaining(it.months_remaining()),
                        theme.ampel_color(key, colors), theme.ampel_soft(key, colors))
            self.table.setCellWidget(r, 4, pill_cell(pill))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # Status column holds a pill cell-widget -> fixed width so it never clips.
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 140)
        align_table_headers(self.table, right_cols=(2,))
        self._panel.update_state()
        self.total.setText(f"Summe (gefiltert): {format_eur(shown_total)}  ·  "
                           f"Gesamt aktiv: {format_eur(self.ctx.fixed.total_active())}")

    def _add(self) -> None:
        dlg = FixedCostDialog(parent=self)
        if dlg.exec():
            self.ctx.fixed.add(dlg.result_model)
            self.ctx.notify_changed()

    def _edit(self) -> None:
        rid = _selected_id(self.table)
        if rid is None:
            return
        item = self.ctx.fixed.get(rid)
        if not item:
            return
        dlg = FixedCostDialog(item, parent=self)
        if dlg.exec():
            self.ctx.fixed.update(dlg.result_model)
            self.ctx.notify_changed()

    def _delete(self) -> None:
        rid = _selected_id(self.table)
        if rid is None:
            return
        if QMessageBox.question(self, "Löschen", "Diesen Fixkosten-Eintrag wirklich löschen?") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.fixed.delete(rid)
            self.ctx.notify_changed()


# --- Variable expenses tab -------------------------------------------------
class _ExpensesTab(QWidget):
    _MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                  "August", "September", "Oktober", "November", "Dezember"]

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        today = date.today()
        self._year, self._month = today.year, today.month

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 14, 2, 2)
        layout.setSpacing(12)

        nav = QHBoxLayout()
        prev = QPushButton("◀")
        prev.setObjectName("Ghost")
        prev.setFixedWidth(40)
        prev.setAccessibleName("Vorheriger Monat")
        prev.setToolTip("Vorheriger Monat")
        nxt = QPushButton("▶")
        nxt.setObjectName("Ghost")
        nxt.setFixedWidth(40)
        nxt.setAccessibleName("Nächster Monat")
        nxt.setToolTip("Nächster Monat")
        self.month_label = QLabel()
        self.month_label.setObjectName("H2")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setMinimumWidth(180)
        prev.clicked.connect(lambda: self._shift(-1))
        nxt.clicked.connect(lambda: self._shift(1))
        nav.addWidget(prev)
        nav.addWidget(self.month_label)
        nav.addWidget(nxt)
        nav.addStretch(1)
        self.total = QLabel()
        self.total.setObjectName("H2")
        nav.addWidget(self.total)
        layout.addLayout(nav)

        bar, add, edit, delete = _toolbar(QLabel(""), "+ Ausgabe")
        layout.addWidget(bar)

        self.table = _make_table(["Datum", "Kategorie", "Beschreibung", "Betrag"])
        self.table.doubleClicked.connect(lambda: self._edit())
        self._panel = TablePanel(
            self.table, "Keine Ausgaben in diesem Monat.",
            "Erfasse über „+ Ausgabe“ deine erste Ausgabe – oder blättere zu einem anderen Monat.")
        layout.addWidget(self._panel, 1)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)

    def _shift(self, delta: int) -> None:
        m = self._month - 1 + delta
        self._year += m // 12
        self._month = m % 12 + 1
        self.refresh()

    def refresh(self) -> None:
        self.month_label.setText(f"{self._MONTHS_DE[self._month - 1]} {self._year}")
        # Month view: one-off expenses of this month + every recurring expense
        # that has started by now (materialised on the fly).
        items = self.ctx.expenses.list_for_month(self._year, self._month)
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            d = _text_item(dates.format_date(it.date))
            d.setData(_ROLE_ID, it.id)
            self.table.setItem(r, 0, d)
            self.table.setItem(r, 1, _text_item(it.category))
            desc = it.description or ""
            if it.recurring:                       # mark the monthly-recurring rows
                desc = f"↻ {desc}" if desc else "↻ monatlich"
            self.table.setItem(r, 2, _text_item(desc))
            self.table.setItem(r, 3, _money_item(it.amount_cents))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in (0, 1, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        align_table_headers(self.table, right_cols=(3,))
        self._panel.update_state()
        self.total.setText(
            f"Summe: {format_eur(self.ctx.expenses.total_for_month(self._year, self._month))}")

    def _add(self) -> None:
        dlg = ExpenseDialog(parent=self)
        if dlg.exec():
            self.ctx.expenses.add(dlg.result_model)
            self.ctx.notify_changed()

    def _edit(self) -> None:
        rid = _selected_id(self.table)
        if rid is None:
            return
        item = self.ctx.expenses.get(rid)
        if not item:
            return
        dlg = ExpenseDialog(item, parent=self)
        if dlg.exec():
            self.ctx.expenses.update(dlg.result_model)
            self.ctx.notify_changed()

    def _delete(self) -> None:
        rid = _selected_id(self.table)
        if rid is None:
            return
        item = self.ctx.expenses.get(rid)
        msg = ("Diese wiederkehrende Ausgabe ganz löschen (in allen Monaten)?"
               if item and item.recurring else "Diese Ausgabe wirklich löschen?")
        if QMessageBox.question(self, "Löschen", msg) == QMessageBox.StandardButton.Yes:
            self.ctx.expenses.delete(rid)
            self.ctx.notify_changed()


class HaushaltsbuchView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(6)
        layout.addWidget(heading("Haushaltsbuch"))
        layout.addWidget(muted("Einnahmen, laufende Fixkosten und variable Ausgaben verwalten."))

        self.tabs = QTabWidget()
        self.income_tab = _IncomeTab(ctx)
        self.fixed_tab = _FixedTab(ctx)
        self.expenses_tab = _ExpensesTab(ctx)
        self.tabs.addTab(self.income_tab, "Einnahmen")
        self.tabs.addTab(self.fixed_tab, "Fixkosten")
        self.tabs.addTab(self.expenses_tab, "Variable Ausgaben")
        self.tabs.currentChanged.connect(self._refresh_current_tab)
        layout.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        # Only the visible tab needs fresh data now; the others reload when the
        # user switches to them (currentChanged), avoiding three DB query sets
        # and three full table rebuilds on every data change.
        self._refresh_current_tab()

    def _refresh_current_tab(self) -> None:
        widget = self.tabs.currentWidget()
        if widget is not None:
            widget.refresh()

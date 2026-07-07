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
    QLineEdit,
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
    EXPENSE_CATEGORIES,
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
from ui.widgets.month_nav import MonthNavigator

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


class _SortItem(QTableWidgetItem):
    """Read-only cell that sorts by an explicit key (ISO date, or integer cents)
    rather than by its displayed German string, so column-click sorting is
    numerically/chronologically correct."""

    def __init__(self, text: str, sort_key, *, right: bool = False) -> None:
        super().__init__(text)
        self._key = sort_key
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if right:
            self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other: "QTableWidgetItem") -> bool:
        other_key = getattr(other, "_key", None)
        if other_key is not None:
            return self._key < other_key
        return super().__lt__(other)


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
        today = date.today()
        self._year, self._month = today.year, today.month

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 14, 2, 2)
        layout.setSpacing(12)

        # Month navigator + running total. The fixed monthly income sources apply
        # to every month and are always shown; only the one-off (imported) credits
        # are scoped to the selected month, so blättering shows that month's extras.
        nav = QHBoxLayout()
        self._nav = MonthNavigator(self.ctx.colors, self._year, self._month, allow_future=True)
        self._nav.month_changed.connect(self._on_month)
        nav.addWidget(self._nav)
        nav.addStretch(1)
        self.total = QLabel()
        self.total.setObjectName("H2")
        nav.addWidget(self.total)
        layout.addLayout(nav)

        bar, add, edit, delete = _toolbar(QLabel(""), "+ Einnahme")
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

    def _on_month(self, year: int, month: int) -> None:
        self._year, self._month = year, month
        self.refresh()

    def refresh(self) -> None:
        self._nav.refresh_icons(self.ctx.colors)   # keep chevrons themed
        colors = self.ctx.colors
        sources = self.ctx.income.list()                              # recurring monthly income
        oneoffs = self.ctx.var_income.list_for_month(self._year, self._month)  # this month's credits
        self.table.setRowCount(len(sources) + len(oneoffs))
        r = 0
        for it in sources:
            name = _text_item(it.name)
            name.setData(_ROLE_ID, ("src", it.id))       # tag the row's origin
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, _text_item(INCOME_TYPE_LABELS.get(it.income_type, "")))
            self.table.setItem(r, 2, _money_item(it.amount_cents))
            key = "green" if it.active else "grey"
            label = "Aktiv" if it.active else "Inaktiv"
            self.table.setCellWidget(r, 3, pill_cell(
                Pill(label, theme.ampel_color(key, colors), theme.ampel_soft(key, colors))))
            r += 1
        for it in oneoffs:
            name = _text_item(it.source or "Einmalige Einnahme")
            name.setData(_ROLE_ID, ("var", it.id))
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, _text_item("Einmalig"))
            self.table.setItem(r, 2, _money_item(it.amount_cents))
            self.table.setCellWidget(r, 3, pill_cell(
                Pill(dates.format_date(it.date) or "einmalig",
                     theme.ampel_color("blue", colors), theme.ampel_soft("blue", colors))))
            r += 1
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # Status hosts a pill cell-widget -> fixed width so it never clips.
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 110)
        align_table_headers(self.table, right_cols=(2,))
        self._panel.update_state()
        oneoff_month = self.ctx.var_income.total_for_month(self._year, self._month)
        text = f"Feste Einnahmen/Monat: {format_eur(self.ctx.income.total_active())}"
        if oneoff_month:
            text += f"  ·  einmalig im Monat: {format_eur(oneoff_month)}"
        self.total.setText(text)

    def _add(self) -> None:
        dlg = IncomeDialog(parent=self)
        if dlg.exec():
            self.ctx.income.add(dlg.result_model)
            self.ctx.notify_changed()

    def _selected(self) -> tuple[str, int] | None:
        """Return (kind, id) of the selected row: 'src' recurring or 'var' one-off."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        data = item.data(_ROLE_ID) if item else None
        return tuple(data) if data else None

    def _edit(self) -> None:
        sel = self._selected()
        if sel is None:
            return
        kind, rid = sel
        if kind == "var":
            QMessageBox.information(
                self, "Einmalige Einnahme",
                "Einmalige (importierte) Einnahmen lassen sich hier nur löschen.")
            return
        item = self.ctx.income.get(rid)
        if not item:
            return
        dlg = IncomeDialog(item, parent=self)
        if dlg.exec():
            self.ctx.income.update(dlg.result_model)
            self.ctx.notify_changed()

    def _delete(self) -> None:
        sel = self._selected()
        if sel is None:
            return
        kind, rid = sel
        if QMessageBox.question(self, "Löschen", "Diese Einnahme wirklich löschen?") \
                == QMessageBox.StandardButton.Yes:
            if kind == "var":
                self.ctx.var_income.delete(rid)
            else:
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
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        today = date.today()
        self._year, self._month = today.year, today.month

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 14, 2, 2)
        layout.setSpacing(12)

        # Row 1: month navigator + running total.
        nav = QHBoxLayout()
        self._nav = MonthNavigator(self.ctx.colors, self._year, self._month, allow_future=True)
        self._nav.month_changed.connect(self._on_month)
        nav.addWidget(self._nav)
        nav.addStretch(1)
        self.total = QLabel()
        self.total.setObjectName("H2")
        nav.addWidget(self.total)
        layout.addLayout(nav)

        # Row 2: cross-month search + category filter. While either is active the
        # table shows matches across ALL months (answering "what did I spend at
        # X this year?"); when both are cleared it returns to the single-month view.
        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen (Beschreibung, über alle Monate) …")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Ausgaben durchsuchen")
        self.search.textChanged.connect(self._on_filter_changed)
        self.cat_filter = QComboBox()
        self.cat_filter.addItem("Alle Kategorien", None)
        for cat in EXPENSE_CATEGORIES:
            self.cat_filter.addItem(cat, cat)
        self.cat_filter.setAccessibleName("Nach Kategorie filtern")
        self.cat_filter.currentIndexChanged.connect(self._on_filter_changed)
        self._reset_btn = QPushButton("Zurücksetzen")
        self._reset_btn.setObjectName("Ghost")
        self._reset_btn.clicked.connect(self._reset_filters)
        filters.addWidget(QLabel("Filter:"))
        filters.addWidget(self.search, 1)
        filters.addWidget(self.cat_filter)
        filters.addWidget(self._reset_btn)
        layout.addLayout(filters)

        bar, add, edit, delete = _toolbar(QLabel(""), "+ Ausgabe")
        layout.addWidget(bar)

        self.table = _make_table(["Datum", "Kategorie", "Beschreibung", "Betrag"])
        self.table.setSortingEnabled(True)   # click a header to sort (correct numeric/date order)
        self.table.doubleClicked.connect(lambda: self._edit())
        self._panel = TablePanel(
            self.table, "Keine Ausgaben gefunden.",
            "Erfasse über „+ Ausgabe“ eine Ausgabe – oder ändere Monat, Suche oder Filter.")
        layout.addWidget(self._panel, 1)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)

    def _on_month(self, year: int, month: int) -> None:
        self._year, self._month = year, month
        self.refresh()

    def _on_filter_changed(self, *_args) -> None:
        self.refresh()

    def _reset_filters(self) -> None:
        blocked = self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(blocked)
        self.cat_filter.setCurrentIndex(0)
        self.refresh()

    def _is_filtering(self) -> bool:
        return bool(self.search.text().strip()) or self.cat_filter.currentData() is not None

    def _filtered_items(self) -> list:
        """Expenses across all months matching the search text and/or category."""
        term = self.search.text().strip().lower()
        cat = self.cat_filter.currentData()
        out = []
        for it in self.ctx.expenses.list_recent(5000):
            if cat and it.category != cat:
                continue
            if term and term not in (it.description or "").lower():
                continue
            out.append(it)
        return out

    def refresh(self) -> None:
        self._nav.refresh_icons(self.ctx.colors)   # keep chevrons themed
        filtering = self._is_filtering()
        # When filtering across months, the month navigator does not apply.
        self._nav.setEnabled(not filtering)
        if filtering:
            items = self._filtered_items()
            total = sum(it.amount_cents for it in items)
            self.total.setText(f"{len(items)} Treffer · Summe {format_eur(total)}")
        else:
            # Month view: one-off expenses of this month + every recurring expense
            # that has started by now (materialised on the fly).
            items = self.ctx.expenses.list_for_month(self._year, self._month)
            self.total.setText(
                f"Summe: {format_eur(self.ctx.expenses.total_for_month(self._year, self._month))}")

        # Sorting must be off while filling, or inserted rows reshuffle mid-loop.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            d = _SortItem(dates.format_date(it.date), it.date)   # sort by ISO date
            d.setData(_ROLE_ID, it.id)
            self.table.setItem(r, 0, d)
            self.table.setItem(r, 1, _text_item(it.category))
            desc = it.description or ""
            if it.recurring:                       # mark the monthly-recurring rows
                desc = f"↻ {desc}" if desc else "↻ monatlich"
            self.table.setItem(r, 2, _text_item(desc))
            self.table.setItem(r, 3, _SortItem(format_eur(it.amount_cents), it.amount_cents, right=True))
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in (0, 1, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        align_table_headers(self.table, right_cols=(3,))
        self._panel.update_state()

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

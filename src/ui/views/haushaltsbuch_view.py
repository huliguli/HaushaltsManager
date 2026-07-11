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

from modules import dates, pots as pots_mod
from modules.models import (
    EXPENSE_CATEGORIES,
    FIXED_CATEGORIES,
    INCOME_TYPE_LABELS,
    PotMovement,
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
    table_shortcuts,
)
from ui.widgets.month_nav import MonthNavigator
from ui.widgets import toast

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
        table_shortcuts(self.table, self._edit, self._delete)
        self._panel = TablePanel(
            self.table, "Noch keine Einnahmen erfasst.",
            "Lege deine erste Einnahmequelle an – sie zählt ab sofort in jeder Monatsübersicht.",
            action_text="+ Einnahme anlegen", on_action=self._add)
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
                != QMessageBox.StandardButton.Yes:
            return
        # Keep the row's dataclass so the toast can re-insert it on undo.
        repo = self.ctx.var_income if kind == "var" else self.ctx.income
        item = repo.get(rid)
        repo.delete(rid)
        self.ctx.notify_changed()
        if item is not None:
            def undo() -> None:
                item.id = None  # re-insert as a new row
                repo.add(item)
                self.ctx.notify_changed()
            toast.show_undo(self, "Einnahme gelöscht.", undo)


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
        table_shortcuts(self.table, self._edit, self._delete)
        self._panel = TablePanel(
            self.table, "Keine Fixkosten in dieser Ansicht.",
            "Lege einen Eintrag an oder ändere den Filter.",
            action_text="+ Fixkosten anlegen", on_action=self._add)
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
            start = dates.parse_date(it.start_date)
            if start and start > dates.today():
                # Not started yet (e.g. a savings plan scheduled for a later month):
                # flag its start instead of the misleading "noch X Monate" (which
                # counts to the end date). It still counts in the budget only from
                # this month on (active_for_month).
                pill = Pill(f"ab {start.month:02d}.{start.year}",
                            theme.ampel_color("blue", colors), theme.ampel_soft("blue", colors))
            else:
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
                != QMessageBox.StandardButton.Yes:
            return
        item = self.ctx.fixed.get(rid)
        self.ctx.fixed.delete(rid)
        self.ctx.notify_changed()
        if item is not None:
            def undo() -> None:
                item.id = None
                self.ctx.fixed.add(item)
                self.ctx.notify_changed()
            toast.show_undo(self, "Fixkosten-Eintrag gelöscht.", undo)


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

        # Row 2: search + category filter + scope. The scope decides whether the
        # filters apply to the selected month or across ALL months; typing a
        # search auto-switches to "Alle Monate" (the classic "what did I spend
        # at X this year?"), the chart drilldown sets month + category scope.
        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen (Beschreibung) …")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Ausgaben durchsuchen")
        self.search.textChanged.connect(self._on_search_changed)
        self.cat_filter = QComboBox()
        self.cat_filter.addItem("Alle Kategorien", None)
        for cat in EXPENSE_CATEGORIES:
            self.cat_filter.addItem(cat, cat)
        self.cat_filter.setAccessibleName("Nach Kategorie filtern")
        self.cat_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.scope = QComboBox()
        self.scope.addItem("Nur gewählter Monat", "month")
        self.scope.addItem("Alle Monate", "all")
        self.scope.setAccessibleName("Suchbereich: gewählter Monat oder alle Monate")
        self.scope.currentIndexChanged.connect(self._on_filter_changed)
        self._reset_btn = QPushButton("Zurücksetzen")
        self._reset_btn.setObjectName("Ghost")
        self._reset_btn.clicked.connect(self._reset_filters)
        filters.addWidget(QLabel("Filter:"))
        filters.addWidget(self.search, 1)
        filters.addWidget(self.cat_filter)
        filters.addWidget(self.scope)
        filters.addWidget(self._reset_btn)
        layout.addLayout(filters)

        bar, add, edit, delete = _toolbar(QLabel(""), "+ Ausgabe")
        layout.addWidget(bar)

        self.table = _make_table(["Datum", "Kategorie", "Beschreibung", "Betrag"])
        self.table.setSortingEnabled(True)   # click a header to sort (correct numeric/date order)
        self.table.doubleClicked.connect(lambda: self._edit())
        table_shortcuts(self.table, self._edit, self._delete)
        self._panel = TablePanel(
            self.table, "Keine Ausgaben gefunden.",
            "Erfasse eine Ausgabe – oder ändere Monat, Suche oder Filter.",
            action_text="+ Ausgabe erfassen", on_action=self._add)
        layout.addWidget(self._panel, 1)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)

    def _on_month(self, year: int, month: int) -> None:
        self._year, self._month = year, month
        self.refresh()

    def _on_filter_changed(self, *_args) -> None:
        self.refresh()

    def _on_search_changed(self, text: str) -> None:
        # Typing a search widens the scope to all months (the classic use case);
        # switching back to the month scope stays a deliberate user choice.
        if text.strip() and self.scope.currentData() == "month":
            blocked = self.scope.blockSignals(True)
            self.scope.setCurrentIndex(1)
            self.scope.blockSignals(blocked)
        self.refresh()

    def _reset_filters(self) -> None:
        for widget in (self.search, self.cat_filter, self.scope):
            widget.blockSignals(True)
        self.search.clear()
        self.cat_filter.setCurrentIndex(0)
        self.scope.setCurrentIndex(0)
        for widget in (self.search, self.cat_filter, self.scope):
            widget.blockSignals(False)
        self.refresh()

    def apply_filter(self, year: int, month: int, category: str | None) -> None:
        """Drilldown entry point: show (year, month), filtered to ``category``.

        A category the combo does not know (e.g. a custom import category)
        falls back to "Alle Kategorien" — the month jump still happens.
        """
        self._year, self._month = year, month
        self._nav.set_month(year, month)
        for widget in (self.search, self.cat_filter, self.scope):
            widget.blockSignals(True)
        self.search.clear()
        self.scope.setCurrentIndex(0)                    # month scope
        index = self.cat_filter.findData(category) if category else 0
        self.cat_filter.setCurrentIndex(index if index >= 0 else 0)
        for widget in (self.search, self.cat_filter, self.scope):
            widget.blockSignals(False)
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
        cross_month = self.scope.currentData() == "all"
        # When filtering across months, the month navigator does not apply.
        self._nav.setEnabled(not cross_month)
        if cross_month:
            items = self._filtered_items()
            total = sum(it.amount_cents for it in items)
            self.total.setText(f"{len(items)} Treffer · Summe {format_eur(total)}")
        else:
            # Month view: one-off expenses of this month + every recurring expense
            # that has started by now (materialised on the fly) — optionally
            # narrowed by category/search (e.g. via chart drilldown).
            items = self.ctx.expenses.list_for_month(self._year, self._month)
            term = self.search.text().strip().lower()
            cat = self.cat_filter.currentData()
            if cat:
                items = [it for it in items if it.category == cat]
            if term:
                items = [it for it in items if term in (it.description or "").lower()]
            if cat or term:
                total = sum(it.amount_cents for it in items)
                self.total.setText(f"{len(items)} Treffer · Summe {format_eur(total)}")
            else:
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
            if it.recurring:                       # mark recurring rows incl. cadence
                if it.interval_months == 1:
                    desc = f"↻ {desc}" if desc else "↻ monatlich"
                else:
                    marker = it.interval_label()   # quartalsweise / jährlich / ...
                    desc = f"↻ {marker}" + (f" · {desc}" if desc else "")
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
        if QMessageBox.question(self, "Löschen", msg) != QMessageBox.StandardButton.Yes:
            return
        self.ctx.expenses.delete(rid)
        self.ctx.notify_changed()
        if item is not None:
            def undo() -> None:
                item.id = None
                self.ctx.expenses.add(item)
                self.ctx.notify_changed()
            text = ("Wiederkehrende Ausgabe gelöscht."
                    if item.recurring else "Ausgabe gelöscht.")
            toast.show_undo(self, text, undo)


# --- Töpfe tab ---------------------------------------------------------------
class _PotsTab(QWidget):
    """Virtual partitions of the savings accounts ("was steckt in der Summe?").

    One table shows accounts as bold group rows (recorded balance, allocated,
    unallocated) with their pots indented beneath. All balances are derived by
    the Qt-free :mod:`modules.pots`. Row identity: _ROLE_ID = ("acc"|"pot", id).
    """

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 14, 2, 2)
        layout.setSpacing(12)

        intro = QLabel(
            "Töpfe unterteilen dein Sparkonto virtuell: Sie zeigen, was in der "
            "einen Summe bei der Bank eigentlich steckt. Tipp: Richte je Topf "
            "einen Dauerauftrag über die Monatsrate ein – dann wächst der Topf "
            "hier automatisch synchron zur Bank.")
        intro.setObjectName("Faint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Summary on its own row — the button bar below would clip it on
        # smaller windows otherwise.
        self.total = QLabel()
        self.total.setObjectName("H2")
        layout.addWidget(self.total)

        bar = QHBoxLayout()
        bar.addStretch(1)
        book = QPushButton("Ein-/Auszahlung")
        book.setObjectName("Ghost")
        transfer = QPushButton("Umbuchen")
        transfer.setObjectName("Ghost")
        edit = QPushButton("Bearbeiten")
        edit.setObjectName("Ghost")
        delete = QPushButton("Löschen")
        delete.setObjectName("Danger")
        add_account = QPushButton("+ Sparkonto")
        add_account.setObjectName("Ghost")
        add_pot = QPushButton("+ Topf")
        add_pot.setObjectName("Primary")
        for btn in (book, transfer, edit, delete, add_account, add_pot):
            bar.addWidget(btn)
        layout.addLayout(bar)

        self.table = _make_table(
            ["Bezeichnung", "Stand", "Monatsrate", "Bewegungen", "Hinweis"])
        self.table.doubleClicked.connect(lambda: self._edit())
        table_shortcuts(self.table, self._edit, self._delete)
        self._panel = TablePanel(
            self.table, "Noch keine Töpfe eingerichtet.",
            "Lege zuerst dein Sparkonto mit dem aktuellen Kontostand an und "
            "teile die Summe dann in Töpfe auf (z. B. Urlaub, Notgroschen, "
            "Auto). Mit einer Monatsrate je Topf – passend zu einem "
            "Dauerauftrag bei deiner Bank – bleibt alles von allein aktuell.",
            action_text="+ Sparkonto anlegen", on_action=self._add_account)
        layout.addWidget(self._panel, 1)

        add_account.clicked.connect(self._add_account)
        add_pot.clicked.connect(self._add_pot)
        book.clicked.connect(self._movement)
        transfer.clicked.connect(self._transfer)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)

    # -- rendering ------------------------------------------------------------
    def refresh(self) -> None:
        colors = self.ctx.colors
        overview = pots_mod.build_overview(
            self.ctx.savings_accounts, self.ctx.pots, self.ctx.pot_moves)
        rows: list = []
        for acc in overview:
            rows.append(("acc", acc))
            for state in acc.pots:
                rows.append(("pot", state))
        self.table.setRowCount(len(rows))
        total_balance = sum(a.account.balance_cents for a in overview)
        total_unallocated = sum(a.unallocated_cents for a in overview)

        for r, (kind, item) in enumerate(rows):
            if kind == "acc":
                account = item.account
                name = _text_item(account.name)
                name.setData(_ROLE_ID, ("acc", account.id))
                font = name.font()
                font.setBold(True)
                name.setFont(font)
                self.table.setItem(r, 0, name)
                stand = _money_item(account.balance_cents)
                stand.setFont(font)
                self.table.setItem(r, 1, stand)
                self.table.setItem(r, 2, _text_item(""))
                self.table.setItem(r, 3, _text_item(
                    f"Stand vom {dates.format_date(account.balance_date) or '–'}"))
                unallocated = item.unallocated_cents
                if unallocated < 0:
                    pill = Pill(f"{format_eur(-unallocated)} zu viel verteilt",
                                theme.ampel_color("red", colors),
                                theme.ampel_soft("red", colors))
                elif unallocated > 0:
                    pill = Pill(f"{format_eur(unallocated)} nicht verteilt",
                                theme.ampel_color("amber", colors),
                                theme.ampel_soft("amber", colors))
                else:
                    pill = Pill("voll verteilt",
                                theme.ampel_color("green", colors),
                                theme.ampel_soft("green", colors))
                self.table.setCellWidget(r, 4, pill_cell(pill))
            else:
                pot = item.pot
                name = _text_item(f"      {pot.name}")
                name.setData(_ROLE_ID, ("pot", pot.id))
                self.table.setItem(r, 0, name)
                self.table.setItem(r, 1, _money_item(item.balance_cents))
                self.table.setItem(r, 2, _text_item(
                    format_eur(pot.monthly_cents) + " / Monat"
                    if pot.monthly_cents else "–"))
                moved = item.moved_cents
                self.table.setItem(r, 3, _text_item(
                    format_eur(moved, plus=True) if moved else "–"))
                hints = []
                if pot.goal_id is not None:
                    goal = self.ctx.goals.get(pot.goal_id)
                    if goal is not None:
                        hints.append(f"Ziel: {goal.name}")
                if pot.note:
                    hints.append(pot.note)
                self.table.setItem(r, 4, _text_item(" · ".join(hints) or "–"))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 230)
        align_table_headers(self.table, right_cols=(1, 2, 3))
        self._panel.update_state()
        summary = f"Gesamt auf Sparkonten: {format_eur(total_balance)}"
        if overview:
            summary += f"  ·  nicht verteilt: {format_eur(total_unallocated)}"
        self.total.setText(summary)

    # -- selection ------------------------------------------------------------
    def _selected(self) -> tuple[str, int] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        data = item.data(_ROLE_ID) if item else None
        return tuple(data) if data else None

    # -- actions --------------------------------------------------------------
    def _add(self) -> None:
        # Ctrl+N routes here: without an account it starts with the account.
        if not self.ctx.savings_accounts.list():
            self._add_account()
        else:
            self._add_pot()

    def _add_account(self) -> None:
        from ui.pot_dialogs import AccountDialog
        dlg = AccountDialog(parent=self)
        if dlg.exec():
            self.ctx.savings_accounts.add(dlg.result_model)
            self.ctx.notify_changed()

    def _add_pot(self) -> None:
        from ui.pot_dialogs import PotDialog
        accounts = self.ctx.savings_accounts.list()
        if not accounts:
            QMessageBox.information(
                self, "Erst das Sparkonto",
                "Lege zuerst dein Sparkonto mit dem aktuellen Kontostand an – "
                "die Töpfe verteilen dann diese Summe.")
            return
        dlg = PotDialog(accounts, self.ctx.goals.list(), parent=self)
        if dlg.exec():
            pot_id = self.ctx.pots.add(dlg.result_model)
            if dlg.start_cents > 0:
                self.ctx.pot_moves.add(PotMovement(
                    pot_id=pot_id, date=dates.to_iso(dates.today()),
                    amount_cents=dlg.start_cents, note="Startbestand"))
            self.ctx.notify_changed()

    def _movement(self) -> None:
        from ui.pot_dialogs import MovementDialog
        pot_list = self.ctx.pots.list()
        if not pot_list:
            QMessageBox.information(self, "Kein Topf",
                                    "Lege zuerst einen Topf an.")
            return
        selected = self._selected()
        preselect = selected[1] if selected and selected[0] == "pot" else None
        dlg = MovementDialog(pot_list, preselect, parent=self)
        if dlg.exec():
            move_id = self.ctx.pot_moves.add(dlg.result_model)
            self.ctx.notify_changed()

            def undo() -> None:
                self.ctx.pot_moves.delete(move_id)
                self.ctx.notify_changed()
            kind = "Einzahlung" if dlg.result_model.amount_cents > 0 else "Entnahme"
            toast.show_undo(self, f"{kind} gebucht.", undo)

    def _transfer(self) -> None:
        from ui.pot_dialogs import TransferDialog
        pot_list = self.ctx.pots.list()
        if len(pot_list) < 2:
            QMessageBox.information(self, "Umbuchen",
                                    "Zum Umbuchen braucht es mindestens zwei Töpfe.")
            return
        dlg = TransferDialog(pot_list, parent=self)
        if dlg.exec():
            src, dst, amount, note = dlg.result
            self.ctx.pot_moves.transfer(
                src, dst, amount, dates.to_iso(dates.today()), note)
            self.ctx.notify_changed()

    def _edit(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        kind, rid = selected
        if kind == "acc":
            account = self.ctx.savings_accounts.get(rid)
            if account is None:
                return
            from ui.pot_dialogs import AccountDialog
            dlg = AccountDialog(account, parent=self)
            if dlg.exec():
                self.ctx.savings_accounts.update(dlg.result_model)
                self.ctx.notify_changed()
        else:
            pot = self.ctx.pots.get(rid)
            if pot is None:
                return
            from ui.pot_dialogs import PotDialog
            dlg = PotDialog(self.ctx.savings_accounts.list(),
                            self.ctx.goals.list(), pot, parent=self)
            if dlg.exec():
                self.ctx.pots.update(dlg.result_model)
                self.ctx.notify_changed()

    def _delete(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        kind, rid = selected
        if kind == "acc":
            account = self.ctx.savings_accounts.get(rid)
            if account is None:
                return
            if QMessageBox.question(
                    self, "Löschen",
                    f"Sparkonto „{account.name}“ samt allen Töpfen und "
                    f"Buchungen löschen?") != QMessageBox.StandardButton.Yes:
                return
            self.ctx.savings_accounts.delete(rid)
            self.ctx.notify_changed()
        else:
            pot = self.ctx.pots.get(rid)
            if pot is None:
                return
            if QMessageBox.question(
                    self, "Löschen",
                    f"Topf „{pot.name}“ samt Buchungen löschen?") \
                    != QMessageBox.StandardButton.Yes:
                return
            self.ctx.pots.delete(rid)
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
        self.pots_tab = _PotsTab(ctx)
        self.tabs.addTab(self.income_tab, "Einnahmen")
        self.tabs.addTab(self.fixed_tab, "Fixkosten")
        self.tabs.addTab(self.expenses_tab, "Variable Ausgaben")
        self.tabs.addTab(self.pots_tab, "Töpfe")
        self.tabs.currentChanged.connect(self._refresh_current_tab)
        layout.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        # Only the visible tab needs fresh data now; the others reload when the
        # user switches to them (currentChanged), avoiding three DB query sets
        # and three full table rebuilds on every data change.
        self._refresh_current_tab()

    def show_expenses_filter(self, year: int, month: int, category: str | None) -> None:
        """Chart drilldown: open the expenses tab filtered to month (+ category)."""
        self.tabs.setCurrentWidget(self.expenses_tab)
        self.expenses_tab.apply_filter(year, month, category)

    def show_pots(self) -> None:
        """Dashboard card link: open the Töpfe tab."""
        self.tabs.setCurrentWidget(self.pots_tab)
        self.pots_tab.refresh()

    def _refresh_current_tab(self) -> None:
        widget = self.tabs.currentWidget()
        if widget is not None:
            widget.refresh()

    # -- keyboard-layer hooks -------------------------------------------------
    def create_new(self) -> bool:
        tab = self.tabs.currentWidget()
        if tab is not None and hasattr(tab, "_add"):
            tab._add()
            return True
        return False

    def focus_search(self) -> bool:
        # The expense search is the only free-text search in the app; jump to
        # its tab so Ctrl+F always lands somewhere useful.
        self.tabs.setCurrentWidget(self.expenses_tab)
        self.expenses_tab.search.setFocus()
        self.expenses_tab.search.selectAll()
        return True

    def month_navigator(self):
        tab = self.tabs.currentWidget()
        return getattr(tab, "_nav", None)

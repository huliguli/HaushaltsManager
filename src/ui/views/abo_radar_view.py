"""Abo-Radar: suspected subscriptions found in the booked one-off expenses.

The detection lives in :mod:`modules.subscriptions` (Qt-free); this view only
renders the findings and offers the two actions: adopt a subscription as a
fixed cost (so it is planned into the budget and the drop-off timeline) or
hide the suggestion. Both are immediately undoable.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from modules import dates, subscriptions
from modules.models import FixedCost
from modules.money import format_eur
from ui import theme
from ui.views.base_view import BaseView
from ui.widgets import toast
from ui.widgets.common import (
    Pill,
    TablePanel,
    align_table_headers,
    heading,
    muted,
    pill_cell,
)

_ROLE_PATTERN = Qt.ItemDataRole.UserRole


def _ro_item(text: str, align_right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class AboRadarView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._found: list[subscriptions.SuspectedSubscription] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(12)

        layout.addWidget(heading("Abo-Radar"))
        layout.addWidget(muted(
            "Erkennt wiederkehrende Zahlungen in deinen Buchungen – rein lokal, "
            "ohne Internet. Übernimm gefundene Abos als Fixkosten oder blende sie aus."))

        bar = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("H2")
        bar.addWidget(self.summary)
        bar.addStretch(1)
        self._restore_btn = QPushButton("Ausgeblendete wieder anzeigen")
        self._restore_btn.setObjectName("Ghost")
        self._restore_btn.clicked.connect(self._restore_hidden)
        bar.addWidget(self._restore_btn)
        hide = QPushButton("Ausblenden")
        hide.setObjectName("Ghost")
        hide.clicked.connect(self._hide_selected)
        bar.addWidget(hide)
        adopt = QPushButton("Als Fixkosten übernehmen")
        adopt.setObjectName("Primary")
        adopt.clicked.connect(self._adopt_selected)
        bar.addWidget(adopt)
        layout.addLayout(bar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Bezeichnung", "Kategorie", "Rhythmus", "Betrag",
             "≈ pro Jahr", "Zuletzt", "Hinweis"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.doubleClicked.connect(lambda: self._adopt_selected())
        self._panel = TablePanel(
            self.table, "Keine Abo-Verdachtsfälle gefunden.",
            "Der Radar braucht mindestens drei regelmäßige Buchungen mit gleichem "
            "Namen – z. B. aus dem Bank-Import. Mit mehr Historie findet er mehr.")
        layout.addWidget(self._panel, 1)

    def refresh(self) -> None:
        colors = self.ctx.colors
        self._found = subscriptions.scan(
            self.ctx.expenses, self.ctx.fixed, self.ctx.sub_ignores)
        self.table.setRowCount(len(self._found))
        yearly_total = 0
        for r, s in enumerate(self._found):
            yearly_total += s.yearly_cents
            name = _ro_item(s.name)
            name.setData(_ROLE_PATTERN, s.pattern)
            name.setToolTip(f"{s.occurrences} Buchungen seit "
                            f"{dates.format_date(s.first_iso)}")
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, _ro_item(s.category))
            self.table.setItem(r, 2, _ro_item(s.interval_label))
            self.table.setItem(r, 3, _ro_item(format_eur(s.amount_cents), True))
            self.table.setItem(r, 4, _ro_item(format_eur(s.yearly_cents), True))
            self.table.setItem(r, 5, _ro_item(dates.format_date(s.last_iso)))
            if s.price_increase is not None:
                pill = Pill("Preis gestiegen",
                            theme.ampel_color("amber", colors),
                            theme.ampel_soft("amber", colors))
                cell = pill_cell(pill)
                cell.setToolTip(
                    f"{format_eur(s.price_increase.old_cents)} → "
                    f"{format_eur(s.price_increase.new_cents)} seit "
                    f"{dates.format_date(s.price_increase.since_iso)}")
                self.table.setCellWidget(r, 6, cell)
            else:
                self.table.setItem(r, 6, _ro_item("–"))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # Pill column holds a cell widget -> fixed width so it is never clipped.
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 150)
        align_table_headers(self.table, right_cols=(3, 4))
        self._panel.update_state()

        self.summary.setText(
            f"{len(self._found)} vermutete Abos · "
            f"geschätzte Jahreskosten {format_eur(yearly_total)}")
        self._restore_btn.setVisible(bool(self.ctx.sub_ignores.all()))

    # -- selection ------------------------------------------------------------
    def _selected(self) -> subscriptions.SuspectedSubscription | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        pattern = item.data(_ROLE_PATTERN) if item else None
        return next((s for s in self._found if s.pattern == pattern), None)

    # -- actions --------------------------------------------------------------
    def _adopt_selected(self) -> None:
        s = self._selected()
        if s is None:
            return
        monthly = s.monthly_cents
        detail = ""
        if s.interval_months != 1:
            detail = (f"\nDie {s.interval_label}e Zahlung von "
                      f"{format_eur(s.amount_cents)} wird dafür auf eine "
                      f"Monatsrate umgerechnet.")
        msg = (f"„{s.name}“ als Fixkosten übernehmen?\n\n"
               f"Monatsrate {format_eur(monthly)} "
               f"(Kategorie „{subscriptions.fixed_category_for(s.category)}“), "
               f"ab {dates.month_name(dates.today().month)} {dates.today().year}."
               f"{detail}\n\n"
               f"Hinweis: Beim Bank-Import taucht die Zahlung weiter als Buchung "
               f"auf – wähle sie dort ab, damit sie nicht doppelt zählt.")
        if QMessageBox.question(self, "Als Fixkosten übernehmen", msg) \
                != QMessageBox.StandardButton.Yes:
            return
        fc = FixedCost(
            name=s.name, amount_cents=monthly,
            category=subscriptions.fixed_category_for(s.category),
            start_date=dates.to_iso(dates.today()),
            note=f"{subscriptions.RADAR_NOTE} "
                 f"({format_eur(s.amount_cents)} {s.interval_label})",
            active=True)
        fixed_id = self.ctx.fixed.add(fc)
        # Adopted = handled; the pattern is parked so the radar stays quiet.
        self.ctx.sub_ignores.add(s.pattern)
        self.ctx.notify_changed()

        def undo() -> None:
            self.ctx.fixed.delete(fixed_id)
            self.ctx.sub_ignores.remove(s.pattern)
            self.ctx.notify_changed()

        toast.show_undo(self, f"„{s.name}“ als Fixkosten übernommen.", undo)

    def _hide_selected(self) -> None:
        s = self._selected()
        if s is None:
            return
        self.ctx.sub_ignores.add(s.pattern)
        self.refresh()

        def undo() -> None:
            self.ctx.sub_ignores.remove(s.pattern)
            self.refresh()

        toast.show_undo(self, f"„{s.name}“ ausgeblendet.", undo)

    def _restore_hidden(self) -> None:
        hidden = self.ctx.sub_ignores.all()
        if not hidden:
            return
        if QMessageBox.question(
                self, "Wieder anzeigen",
                f"{len(hidden)} ausgeblendete Vorschläge wieder anzeigen?\n"
                f"Auch bereits übernommene Abos tauchen dann wieder auf.") \
                != QMessageBox.StandardButton.Yes:
            return
        self.ctx.sub_ignores.clear()
        self.refresh()

"""Kredite: manage running loans, with optional sync to a fixed-cost entry.

When a credit is linked to a fixed-cost row, saving the credit keeps that row's
monthly amount in step with the credit's instalment, so the household budget and
the loan list never drift apart.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules import credit_progress, dates
from modules.models import CREDIT_STATUS_LABELS
from modules.money import format_eur
from ui import theme
from ui.dialogs import CreditDialog
from ui.views.base_view import BaseView
from ui.widgets import toast
from ui.widgets.common import (
    Pill,
    TablePanel,
    align_table_headers,
    heading,
    muted,
    pill_cell,
    table_shortcuts,
)

_ROLE_ID = Qt.ItemDataRole.UserRole
_STATUS_AMPEL = {"aktiv": "blue", "abbezahlt": "green", "pausiert": "grey"}


def _ro_item(text: str, align_right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class KrediteView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(12)

        layout.addWidget(heading("Kredite"))
        layout.addWidget(muted("Laufende Kredite verwalten – optional mit Fixkosten verknüpft."))

        bar = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("H2")
        bar.addWidget(self.summary)
        bar.addStretch(1)
        edit = QPushButton("Bearbeiten")
        edit.setObjectName("Ghost")
        delete = QPushButton("Löschen")
        delete.setObjectName("Danger")
        add = QPushButton("+ Kredit")
        add.setObjectName("Primary")
        bar.addWidget(edit)
        bar.addWidget(delete)
        bar.addWidget(add)
        layout.addLayout(bar)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Bezeichnung", "Kategorie", "Gesamtbetrag", "Rate / Monat",
             "Restschuld", "Restlaufzeit", "Ende", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.doubleClicked.connect(lambda: self._edit())
        table_shortcuts(self.table, self._edit, self._delete)
        self._panel = TablePanel(
            self.table, "Noch keine Kredite erfasst.",
            "Lege deinen ersten Eintrag an – auch die Rechner können eine "
            "Finanzierung direkt als Kredit übernehmen.",
            action_text="+ Kredit anlegen", on_action=self._add)
        layout.addWidget(self._panel, 1)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        delete.clicked.connect(self._delete)

    def create_new(self) -> bool:
        self._add()
        return True

    def refresh(self) -> None:
        colors = self.ctx.colors
        credits = self.ctx.credits.list()
        self.table.setRowCount(len(credits))
        monthly_total = 0
        active_count = 0
        remaining_total = 0
        for r, cr in enumerate(credits):
            if cr.status == "aktiv" and cr.monthly_cents:
                monthly_total += cr.monthly_cents
                active_count += 1
            name = _ro_item(cr.name)
            name.setData(_ROLE_ID, cr.id)
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, _ro_item(cr.category))
            self.table.setItem(r, 2, _ro_item(format_eur(cr.total_cents) if cr.total_cents else "–", True))
            self.table.setItem(r, 3, _ro_item(format_eur(cr.monthly_cents) if cr.monthly_cents else "–", True))

            # Scheduled repayment state derived from the master data alone;
            # None when it is too thin (no start/rate/term) -> show a dash.
            progress = credit_progress.compute(cr)
            if progress is not None:
                remaining_total += progress.remaining_cents
                self.table.setCellWidget(r, 4, self._remaining_cell(progress, colors))
            else:
                self.table.setItem(r, 4, _ro_item("–", True))

            self.table.setItem(r, 5, _ro_item(self._term_text(cr)))
            self.table.setItem(r, 6, _ro_item(dates.format_date(cr.end_date) or "–"))
            # Display-only auto status: once the schedule is through, show
            # "Abbezahlt" even while the stored status still says "aktiv"
            # (the row itself stays untouched — editing keeps all options).
            status = cr.status
            if progress is not None and progress.finished and status == "aktiv":
                status = "abbezahlt"
            key = _STATUS_AMPEL.get(status, "grey")
            pill = Pill(CREDIT_STATUS_LABELS.get(status, status),
                        theme.ampel_color(key, colors), theme.ampel_soft(key, colors))
            self.table.setCellWidget(r, 7, pill_cell(pill))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # Cell-widget columns (remaining-debt bar, status pill): ResizeToContents
        # cannot measure widgets -> fixed widths so nothing is ever clipped.
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 150)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(7, 120)
        align_table_headers(self.table, right_cols=(2, 3))
        self._panel.update_state()
        summary = f"{active_count} aktive Kredite · monatliche Belastung {format_eur(monthly_total)}"
        if remaining_total:
            summary += f" · Restschuld gesamt {format_eur(remaining_total)}"
        self.summary.setText(summary)

    @staticmethod
    def _remaining_cell(progress, colors) -> QWidget:
        """Remaining debt + paid share on one line, thin repayment bar below."""
        pct = round(progress.ratio * 100)
        label = QLabel(f"{format_eur(progress.remaining_cents)} · {pct} %")
        label.setStyleSheet(f"color: {colors['text']}; font-size: 11px;")
        label.setFixedHeight(15)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(round(progress.ratio * 1000))
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        color = colors["green"] if progress.finished else colors["primary"]
        bar.setStyleSheet(
            f"QProgressBar {{ background: {colors['surface_3']}; border: none;"
            f" border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}")
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(6, 0, 10, 0)
        layout.setSpacing(3)
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addWidget(bar)
        layout.addStretch(1)
        wrap.setAccessibleName(
            f"Restschuld {format_eur(progress.remaining_cents)}, "
            f"getilgt {pct} Prozent")
        wrap.setToolTip(
            f"Getilgt {format_eur(progress.paid_cents)} von "
            f"{format_eur(progress.principal_cents)} · Rate {progress.months_elapsed} "
            f"von {progress.months_total}")
        return wrap

    @staticmethod
    def _term_text(cr) -> str:
        if cr.end_date:
            rem = dates.months_remaining(cr.end_date)
            if rem is not None and rem >= 0:
                return dates.format_months_remaining(rem)
        if cr.term_months:
            return f"{cr.term_months} Monate"
        return "–"

    # -- actions ------------------------------------------------------------
    def _add(self) -> None:
        dlg = CreditDialog(fixed_costs=self.ctx.fixed.list(), parent=self)
        if dlg.exec():
            cid = self.ctx.credits.add(dlg.result_model)
            self._sync_linked_fixed(self.ctx.credits.get(cid))
            self.ctx.notify_changed()

    def _edit(self) -> None:
        rid = self._selected_id()
        if rid is None:
            return
        cr = self.ctx.credits.get(rid)
        if not cr:
            return
        dlg = CreditDialog(cr, fixed_costs=self.ctx.fixed.list(), parent=self)
        if dlg.exec():
            self.ctx.credits.update(dlg.result_model)
            self._sync_linked_fixed(dlg.result_model)
            self.ctx.notify_changed()

    def _delete(self) -> None:
        rid = self._selected_id()
        if rid is None:
            return
        if QMessageBox.question(self, "Löschen", "Diesen Kredit wirklich löschen?") \
                != QMessageBox.StandardButton.Yes:
            return
        item = self.ctx.credits.get(rid)
        self.ctx.credits.delete(rid)
        self.ctx.notify_changed()
        if item is not None:
            def undo() -> None:
                # The linked fixed-cost row (if any) was not deleted, so the
                # restored credit keeps pointing at it.
                item.id = None
                self.ctx.credits.add(item)
                self.ctx.notify_changed()
            toast.show_undo(self, "Kredit gelöscht.", undo)

    def _sync_linked_fixed(self, credit) -> None:
        """Keep the linked fixed-cost row's monthly amount in sync."""
        if credit is None or credit.linked_fixed_cost_id is None or not credit.monthly_cents:
            return
        fc = self.ctx.fixed.get(credit.linked_fixed_cost_id)
        if fc and fc.amount_cents != credit.monthly_cents:
            fc.amount_cents = credit.monthly_cents
            self.ctx.fixed.update(fc)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(_ROLE_ID) if item else None

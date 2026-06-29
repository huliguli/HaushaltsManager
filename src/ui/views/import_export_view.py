"""Import / Export: Excel & PDF import, Excel & PDF export, quick-setup wizard."""

from __future__ import annotations

import os
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from modules import budget
from modules.file_handler import excel_io, pdf_import, pdf_report
from ui import icons
from ui.import_dialogs import MappingDialog, PdfImportDialog
from ui.views.base_view import BaseView
from ui.wizard import run_wizard
from ui.widgets.common import heading, muted

_MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"]


class ImportExportView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(16)
        layout.addWidget(heading("Import / Export"))
        layout.addWidget(muted("Daten aus Excel oder PDF einlesen und Berichte erzeugen."))

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self._import_card(), 1)
        cards.addWidget(self._export_card(), 1)
        layout.addLayout(cards)
        layout.addStretch(1)

    # -- cards --------------------------------------------------------------
    def _import_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addWidget(self._card_title("download", "Importieren"))
        layout.addWidget(self._action(
            "Excel-Datei importieren",
            "Bankexporte (DKB, Sparkasse, N26 …) mit automatischer Spaltenerkennung.",
            "Excel wählen…", self._import_excel))
        layout.addWidget(self._action(
            "PDF importieren",
            "Kontoauszüge oder Verträge – Beträge werden erkannt und sind korrigierbar.",
            "PDF wählen…", self._import_pdf))
        layout.addWidget(self._action(
            "Quick-Setup-Wizard",
            "Schritt für Schritt Einnahmen, Fixkosten und erste Ausgaben einrichten.",
            "Assistent starten", self._run_wizard))
        layout.addStretch(1)
        return card

    def _export_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addWidget(self._card_title("upload", "Exportieren"))
        layout.addWidget(self._action(
            "Excel-Export",
            "Alle Daten in eine Arbeitsmappe: Übersicht, Timeline, Ausgaben, Kredite, Tilgungspläne.",
            "Als Excel speichern…", self._export_excel))
        layout.addWidget(self._action(
            "PDF-Monatsbericht",
            "Zusammenfassung des aktuellen Monats mit Tabellen und Diagramm.",
            "Als PDF speichern…", self._export_pdf))
        layout.addStretch(1)
        return card

    def _card_title(self, icon_name: str, text: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        ico = QLabel()
        ico.setPixmap(icons.pixmap(icon_name, self.ctx.colors["primary"], 22))
        title = QLabel(text)
        title.setObjectName("H2")
        layout.addWidget(ico)
        layout.addWidget(title)
        layout.addStretch(1)
        return row

    def _action(self, title: str, desc: str, button_text: str, slot) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; font-size: 15px;")
        d = QLabel(desc)
        d.setObjectName("Faint")
        d.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(d)
        btn = QPushButton(button_text)
        btn.setObjectName("Primary")
        btn.clicked.connect(slot)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn)
        layout.addLayout(row)
        return frame

    # -- import handlers ----------------------------------------------------
    def _import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Excel-Datei wählen", "", "Excel (*.xlsx *.xls)")
        if not path:
            return
        try:
            headers, rows, guess = excel_io.read_preview(path)
            if not rows:
                QMessageBox.information(self, "Import", "Die Datei enthält keine Datenzeilen.")
                return
            dlg = MappingDialog(headers, rows, guess, self)
            if not dlg.exec():
                return
            expenses, skipped = excel_io.rows_to_expenses(
                rows, dlg.mapping(), dlg.default_category())
            for e in expenses:
                self.ctx.expenses.add(e)
            self.ctx.notify_changed()
            QMessageBox.information(
                self, "Import abgeschlossen",
                f"{len(expenses)} Ausgaben importiert."
                + (f"\n{skipped} Zeilen übersprungen (nicht lesbar)." if skipped else ""))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import fehlgeschlagen", f"Die Datei konnte nicht gelesen werden.\n\n{exc}")

    def _import_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "PDF wählen", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            amounts = pdf_import.extract_amounts(path)
            if not amounts:
                QMessageBox.information(self, "PDF-Import", "Es wurden keine Beträge erkannt.")
                return
            dlg = PdfImportDialog(amounts, self)
            if not dlg.exec():
                return
            expenses = dlg.selected_expenses()
            for e in expenses:
                self.ctx.expenses.add(e)
            self.ctx.notify_changed()
            QMessageBox.information(self, "Import abgeschlossen", f"{len(expenses)} Beträge übernommen.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import fehlgeschlagen", f"Das PDF konnte nicht gelesen werden.\n\n{exc}")

    def _run_wizard(self) -> None:
        run_wizard(self.ctx, self)

    # -- export handlers ----------------------------------------------------
    def _export_excel(self) -> None:
        default = f"HaushaltsManager-Export-{date.today():%Y-%m-%d}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Excel-Export speichern", default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            out = excel_io.export_workbook(
                path, income=self.ctx.income.list(), fixed_costs=self.ctx.fixed.list(),
                expenses=self.ctx.expenses.list_recent(5000), credits=self.ctx.credits.list(),
                overview=self.ctx.overview())
            self._export_done(str(out))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export fehlgeschlagen", f"Die Datei konnte nicht erstellt werden.\n\n{exc}")

    def _export_pdf(self) -> None:
        today = date.today()
        default = f"Monatsbericht-{today:%Y-%m}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "PDF-Bericht speichern", default, "PDF (*.pdf)")
        if not path:
            return
        try:
            start, end = budget.month_bounds(today.year, today.month)
            out = pdf_report.generate_monthly_report(
                path, year=today.year, month=today.month, overview=self.ctx.overview(),
                fixed_costs=self.ctx.fixed.list(),
                expenses=self.ctx.expenses.list_for_range(start, end),
                credits=self.ctx.credits.list())
            self._export_done(str(out))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export fehlgeschlagen", f"Der Bericht konnte nicht erstellt werden.\n\n{exc}")

    def _export_done(self, path: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Export abgeschlossen")
        box.setText(f"Gespeichert unter:\n{path}")
        open_btn = box.addButton("Ordner öffnen", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Schließen", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            try:
                os.startfile(os.path.dirname(path))  # noqa: S606 - opening a folder we just wrote
            except Exception:  # noqa: BLE001
                pass

    def refresh(self) -> None:
        pass

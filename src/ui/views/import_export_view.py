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

from modules import dates, platform_util
from modules.bank_import import parsers as bank_parsers
from modules.bank_import.categorize import Categorizer
from modules.bank_import.commit import commit_transactions
from modules.bank_import.model import transaction_hash
from modules.file_handler import excel_io, pdf_import, pdf_report
from ui import icons
from ui.bank_import_dialogs import BankCsvMappingDialog, BankReviewDialog
from ui.import_dialogs import MappingDialog, PdfImportDialog
from ui.views.base_view import BaseView
from ui.wizard import run_wizard
from ui.widgets.common import heading, muted
from ui.widgets.month_nav import MonthNavigator


class ImportExportView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        today = date.today()
        self._export_year, self._export_month = today.year, today.month
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(16)
        layout.addWidget(heading("Import / Export"))
        layout.addWidget(muted("Kontoauszüge, Excel oder PDF einlesen und Berichte erzeugen."))

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
            "Kontoauszug importieren",
            "CAMT, MT940, CSV oder PDF – Buchungen werden erkannt und automatisch "
            "Kategorien vorgeschlagen. Alles bleibt lokal auf diesem Gerät.",
            "Auszug wählen…", self._import_bank_statement))
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

        # Month picker: both reports are generated for the chosen month, so past
        # months can be downloaded too (not only the current one).
        picker = QFrame()
        picker.setObjectName("Panel")
        pl = QHBoxLayout(picker)
        pl.setContentsMargins(14, 8, 14, 8)
        pl.setSpacing(10)
        lbl = QLabel("Monat für den Bericht")
        lbl.setObjectName("FieldLabel")
        pl.addWidget(lbl)
        pl.addStretch(1)
        self._export_nav = MonthNavigator(
            self.ctx.colors, self._export_year, self._export_month, allow_future=False)
        self._export_nav.month_changed.connect(self._on_export_month)
        pl.addWidget(self._export_nav)
        layout.addWidget(picker)

        layout.addWidget(self._action(
            "Excel-Monatsüberblick",
            "Übersicht des gewählten Monats + Fixkosten, Kredite, Tilgungspläne und Monatsverlauf.",
            "Als Excel speichern…", self._export_excel))
        layout.addWidget(self._action(
            "PDF-Monatsbericht",
            "Zusammenfassung des gewählten Monats mit Tabellen und Diagramm.",
            "Als PDF speichern…", self._export_pdf))
        layout.addStretch(1)
        return card

    def _on_export_month(self, year: int, month: int) -> None:
        self._export_year, self._export_month = year, month

    def on_theme_changed(self) -> None:
        # Re-tint the month navigator's chevrons for the new theme.
        if hasattr(self, "_export_nav"):
            self._export_nav.refresh_icons(self.ctx.colors)

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

    # -- bank statement import ----------------------------------------------
    def _import_bank_statement(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Kontoauszug wählen", "",
            "Kontoauszüge (*.xml *.camt *.sta *.mt940 *.txt *.csv *.pdf);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            transactions = self._parse_statement(path)
        except bank_parsers.BankImportError as exc:
            QMessageBox.warning(self, "Import", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - a bad file must never crash the app
            QMessageBox.critical(self, "Import fehlgeschlagen",
                                 f"Die Datei konnte nicht verarbeitet werden.\n\n{exc}")
            return
        if transactions is None:  # user cancelled the CSV column mapping
            return

        # Suggest categories from learned + seed rules, then drop already-imported.
        Categorizer(self.ctx.import_rules.rules()).categorize_all(transactions)
        hashes = [transaction_hash(t) for t in transactions]
        known = self.ctx.import_log.known(hashes)
        new_txs = [t for t, h in zip(transactions, hashes) if h not in known]
        skipped = len(transactions) - len(new_txs)
        if not new_txs:
            QMessageBox.information(
                self, "Import",
                f"Alle {len(transactions)} Buchungen wurden bereits importiert.")
            return

        dlg = BankReviewDialog(new_txs, skipped, self.ctx.colors, self)
        if dlg.exec():
            self._commit_bank(dlg.accepted_transactions(), skipped)

    def _parse_statement(self, path: str):
        """Detect format and parse; returns transactions, or None if CSV mapping
        was cancelled. Raises BankImportError with a user message on bad input."""
        fmt = bank_parsers.detect_format(path)
        if fmt == "camt":
            return bank_parsers.parse_camt(path)
        if fmt == "mt940":
            return bank_parsers.parse_mt940(path)
        if fmt == "pdf":
            return bank_parsers.parse_pdf(path)
        headers, rows = bank_parsers.read_csv_rows(path)
        guess = bank_parsers.guess_csv_mapping(headers)
        dlg = BankCsvMappingDialog(headers, rows, guess, self.ctx.bank_profiles, self)
        if not dlg.exec():
            return None
        return bank_parsers.parse_csv(rows, dlg.mapping())

    def _commit_bank(self, transactions, skipped: int) -> None:
        """Write confirmed transactions, learn rules and log them for de-dup.

        The routing lives in the Qt-free :func:`commit_transactions` so it can be
        regression-tested (imported credit -> one-off income, never recurring).
        """
        n_exp, n_inc = commit_transactions(
            transactions, self.ctx.expenses, self.ctx.var_income,
            self.ctx.import_rules, self.ctx.import_log)
        self.ctx.notify_changed()
        QMessageBox.information(
            self, "Import abgeschlossen",
            f"{n_exp} Ausgaben und {n_inc} einmalige Einnahmen übernommen."
            + (f"\n{skipped} bereits vorhanden (übersprungen)." if skipped else ""))

    # -- export handlers ----------------------------------------------------
    def _export_excel(self) -> None:
        y, m = self._export_year, self._export_month
        month_label = f"{dates.month_name(m)} {y}"
        default = f"HaushaltsManager-Monatsuebersicht-{y:04d}-{m:02d}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Excel-Monatsüberblick speichern", default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            out = excel_io.export_workbook(
                path, income=self.ctx.income.list(), fixed_costs=self.ctx.fixed.list(),
                expenses=self.ctx.expenses.list_for_month(y, m),
                history_expenses=self.ctx.expenses.list_recent(5000),
                credits=self.ctx.credits.list(),
                overview=self.ctx.overview(y, m), month_label=month_label)
            self._export_done(str(out))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export fehlgeschlagen", f"Die Datei konnte nicht erstellt werden.\n\n{exc}")

    def _export_pdf(self) -> None:
        y, m = self._export_year, self._export_month
        default = f"Monatsbericht-{y:04d}-{m:02d}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "PDF-Bericht speichern", default, "PDF (*.pdf)")
        if not path:
            return
        try:
            out = pdf_report.generate_monthly_report(
                path, year=y, month=m, overview=self.ctx.overview(y, m),
                fixed_costs=self.ctx.fixed.list(),
                expenses=self.ctx.expenses.list_for_month(y, m),
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
            platform_util.open_path(os.path.dirname(path))

    def refresh(self) -> None:
        pass

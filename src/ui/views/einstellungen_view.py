"""Einstellungen: design, update checking, data management and about."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_meta import APP_DISPLAY_NAME, APP_VERSION, GITHUB_REPO, data_dir, logs_dir
from modules.updater import updater
from ui.views.base_view import BaseView
from ui.wizard import run_wizard
from ui.widgets.common import heading, muted


class EinstellungenView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._checker = None
        self._installer = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(16)
        layout.addWidget(heading("Einstellungen"))
        layout.addWidget(muted("Design, Updates und deine Daten."))

        layout.addWidget(self._design_card())
        layout.addWidget(self._update_card())
        layout.addWidget(self._data_card())
        layout.addWidget(self._about_card())
        layout.addStretch(1)

    # -- design -------------------------------------------------------------
    def _design_card(self) -> QFrame:
        card, layout = self._card("Design")
        row = QHBoxLayout()
        row.addWidget(QLabel("Farbschema:"))
        self._light_btn = QPushButton("Hell")
        self._dark_btn = QPushButton("Dunkel")
        for btn, name in ((self._light_btn, "light"), (self._dark_btn, "dark")):
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c, n=name: self.ctx.set_theme(n))
        row.addWidget(self._light_btn)
        row.addWidget(self._dark_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self._sync_theme_buttons()
        return card

    def _sync_theme_buttons(self) -> None:
        is_dark = self.ctx.theme_name == "dark"
        self._light_btn.setChecked(not is_dark)
        self._dark_btn.setChecked(is_dark)
        self._light_btn.setObjectName("Primary" if not is_dark else "Ghost")
        self._dark_btn.setObjectName("Primary" if is_dark else "Ghost")
        # Re-polish so the objectName change takes effect.
        for btn in (self._light_btn, self._dark_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # -- updates ------------------------------------------------------------
    def _update_card(self) -> QFrame:
        card, layout = self._card("Updates")
        self._auto_check = QCheckBox("Beim Start automatisch nach Updates suchen")
        self._auto_check.setChecked(bool(self.ctx.config.get("update_check_enabled", True)))
        self._auto_check.toggled.connect(
            lambda v: self.ctx.config.set("update_check_enabled", bool(v)))
        layout.addWidget(self._auto_check)

        row = QHBoxLayout()
        self._version_label = QLabel(f"Installierte Version: v{APP_VERSION}")
        self._version_label.setObjectName("Muted")
        row.addWidget(self._version_label)
        row.addStretch(1)
        self._check_btn = QPushButton("Jetzt nach Updates suchen")
        self._check_btn.setObjectName("Ghost")
        self._check_btn.clicked.connect(self._check_now)
        row.addWidget(self._check_btn)
        layout.addLayout(row)

        self._update_status = QLabel("")
        self._update_status.setObjectName("Faint")
        layout.addWidget(self._update_status)
        return card

    def _check_now(self) -> None:
        self._check_btn.setEnabled(False)
        self._update_status.setText("Suche nach Updates …")
        self._checker = updater.UpdateChecker(GITHUB_REPO, APP_VERSION)
        self._checker.result.connect(self._on_check_result)
        self._checker.start()

    def _on_check_result(self, info) -> None:
        self._check_btn.setEnabled(True)
        if info is None:
            self._update_status.setText(
                "Du verwendest die neueste Version (oder es besteht keine Internetverbindung).")
            return
        self._update_status.setText(f"Neue Version verfügbar: v{info.version}")
        self.show_update_dialog(info)

    def show_update_dialog(self, info) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Update verfügbar")
        box.setText(f"Version v{info.version} ist verfügbar.")
        box.setInformativeText("Änderungen anzeigen über „Details“.")
        box.setDetailedText(info.notes)
        install = box.addButton("Herunterladen & installieren", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Später", QMessageBox.ButtonRole.RejectRole)
        skip = box.addButton("Diese Version überspringen", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is skip:
            self.ctx.config.set("skipped_version", info.tag)
        elif clicked is install:
            self._install(info)

    def _install(self, info) -> None:
        if not info.asset_url:
            QMessageBox.information(
                self, "Update", "Im Release ist keine .exe enthalten. Bitte manuell von der "
                "Release-Seite herunterladen.")
            return
        progress = QProgressDialog("Update wird heruntergeladen …", "Abbrechen", 0, 100, self)
        progress.setWindowTitle("Update")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(False)

        self._installer = updater.UpdateInstaller(info.asset_url)
        self._installer.progress.connect(progress.setValue)
        self._installer.failed.connect(lambda msg: self._install_failed(progress, msg))
        self._installer.ready.connect(lambda path: self._install_ready(progress, path))
        # Cooperative cancel (never QThread.terminate(), which would corrupt state
        # and leak the half-downloaded file).
        progress.canceled.connect(self._installer.cancel)
        self._installer.start()

    def _install_failed(self, progress, msg: str) -> None:
        progress.close()
        QMessageBox.warning(self, "Update fehlgeschlagen", f"Der Download ist fehlgeschlagen:\n{msg}")

    def _install_ready(self, progress, path: str) -> None:
        progress.close()
        if updater.apply_update_and_restart(path):
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().quit()
        else:
            QMessageBox.information(
                self, "Update", "Das Update wurde geladen. Im Entwicklungsmodus erfolgt kein "
                "automatischer Austausch – bitte die neue Release-EXE verwenden.")

    # -- data ---------------------------------------------------------------
    def _data_card(self) -> QFrame:
        card, layout = self._card("Daten")
        layout.addWidget(self._data_row(
            "Quick-Setup-Wizard erneut starten",
            "Assistent öffnen", lambda: run_wizard(self.ctx, self), primary=True))
        layout.addWidget(self._data_row(
            "Speicherort der Daten öffnen",
            "Ordner öffnen", lambda: self._open(data_dir())))
        layout.addWidget(self._data_row(
            "Protokoll (Logdatei) öffnen",
            "Protokoll öffnen", lambda: self._open(logs_dir())))
        layout.addWidget(self._data_row(
            "Alle Finanzdaten unwiderruflich löschen",
            "Alle Daten löschen", self._wipe_data, danger=True))
        return card

    def _data_row(self, label: str, button_text: str, slot, primary=False, danger=False) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addStretch(1)
        btn = QPushButton(button_text)
        btn.setObjectName("Primary" if primary else ("Danger" if danger else "Ghost"))
        btn.clicked.connect(slot)
        layout.addWidget(btn)
        return row

    def _wipe_data(self) -> None:
        if QMessageBox.warning(
            self, "Alle Daten löschen",
            "Wirklich ALLE Einnahmen, Fixkosten, Ausgaben und Kredite löschen?\n"
            "Das kann nicht rückgängig gemacht werden.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if QMessageBox.warning(
            self, "Letzte Sicherheitsfrage", "Endgültig löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        for table in ("variable_expenses", "fixed_costs", "income_sources",
                      "credits", "monthly_summary"):
            self.ctx.db.execute(f"DELETE FROM {table}")
        self.ctx.notify_changed()
        QMessageBox.information(self, "Gelöscht", "Alle Finanzdaten wurden entfernt.")

    @staticmethod
    def _open(path) -> None:
        try:
            os.startfile(str(path))  # noqa: S606 - opening a known local folder
        except Exception:  # noqa: BLE001
            pass

    # -- about --------------------------------------------------------------
    def _about_card(self) -> QFrame:
        card, layout = self._card("Über")
        info = QLabel(
            f"{APP_DISPLAY_NAME}  ·  Version v{APP_VERSION}\n"
            f"Repository: github.com/{GITHUB_REPO}\n\n"
            "Privat genutztes Werkzeug. Oberfläche mit PyQt6 (GPL-Lizenz). "
            "Alle Daten bleiben lokal auf diesem Gerät.")
        info.setObjectName("Muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        return card

    # -- helpers ------------------------------------------------------------
    def _card(self, title: str):
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        header = QLabel(title)
        header.setObjectName("H2")
        layout.addWidget(header)
        return card, layout

    def refresh(self) -> None:
        if hasattr(self, "_light_btn"):
            self._sync_theme_buttons()

    def on_theme_changed(self) -> None:
        self._sync_theme_buttons()

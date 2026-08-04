"""Einstellungen: design, update checking, data management and about."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app_meta import APP_DISPLAY_NAME, APP_VERSION, GITHUB_REPO, data_dir, logs_dir
from modules import backup, platform_util
from modules.db_handler.database import CURRENT_SCHEMA_VERSION
from modules.updater import updater
from ui.views.base_view import BaseView
from ui.wizard import run_wizard
from ui.widgets.common import heading, muted, primary_button_qss


class EinstellungenView(BaseView):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._checker = None
        self._installer = None
        # Versions the user postponed with „Später“ — respected by the hourly
        # background check for the rest of the session (a restart asks again).
        self.session_dismissed: set[str] = set()
        self._dialog_open = False
        self._primary_row_btns: list[QPushButton] = []

        # Six cards no longer fit a small window, so the whole view scrolls
        # (same transparent pattern as the dashboard).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll)
        container = QWidget()
        container.setObjectName("ScrollBody")
        # Scoped by object name on purpose: a selector-less rule
        # would cascade onto every card inside and blank its fill.
        container.setStyleSheet("QWidget#ScrollBody { background: transparent; }")
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(16)
        layout.addWidget(heading("Einstellungen"))
        layout.addWidget(muted("Design, Updates und deine Daten."))

        layout.addWidget(self._design_card())
        layout.addWidget(self._update_card())
        layout.addWidget(self._import_card())
        layout.addWidget(self._backup_card())
        layout.addWidget(self._interop_card())
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
        # The active button carries its fill INLINE: the view now lives on a
        # transparent scroll container, where the global #Primary rule does
        # not get painted (see common.primary_button_qss).
        active = self._dark_btn if is_dark else self._light_btn
        inactive = self._light_btn if is_dark else self._dark_btn
        active.setStyleSheet(primary_button_qss(self.ctx.colors))
        inactive.setStyleSheet("")
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

        # Opt-in one step further: found updates install themselves. The same
        # safety net as the manual path applies (checksum + fail-closed
        # Authenticode pin) — only the confirmation dialog is skipped.
        self._auto_install = QCheckBox("Gefundene Updates automatisch installieren")
        self._auto_install.setChecked(bool(self.ctx.config.get("update_auto_install", False)))
        self._auto_install.setEnabled(self._auto_check.isChecked())
        self._auto_install.toggled.connect(
            lambda v: self.ctx.config.set("update_auto_install", bool(v)))
        self._auto_check.toggled.connect(self._auto_install.setEnabled)
        layout.addWidget(self._auto_install)
        auto_hint = QLabel(
            "Ohne Nachfrage: Das Update wird beim Start heruntergeladen, "
            "Prüfsumme und Signatur werden geprüft, danach startet die App neu.")
        auto_hint.setObjectName("Faint")
        auto_hint.setWordWrap(True)
        layout.addWidget(auto_hint)

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
        self._checker = updater.UpdateChecker(GITHUB_REPO, APP_VERSION, parent=self)
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

    def auto_install(self, info) -> None:
        """Startup auto-update (opt-in): install without the confirmation dialog.

        Reuses the exact manual pipeline — download with progress, checksum
        verification, fail-closed signature check — only the question is skipped.
        """
        self._update_status.setText(
            f"Update auf v{info.version} wird automatisch installiert …")
        self._install(info)

    def show_update_dialog(self, info) -> None:
        # The hourly background check may fire while a dialog is already up —
        # never stack a second one onto it.
        if self._dialog_open:
            return
        from ui.update_dialog import UpdateDialog
        dlg = UpdateDialog(info, self.ctx.colors, self)
        self._dialog_open = True
        try:
            dlg.exec()
        finally:
            self._dialog_open = False
        if dlg.choice == "skip":
            self.ctx.config.set("skipped_version", info.tag)
        elif dlg.choice == "install":
            self._install(info)
        else:
            # „Später“: quiet for the rest of the session (per version).
            self.session_dismissed.add(info.tag)

    def update_flow_active(self) -> bool:
        """True while an update dialog or download is in progress."""
        return self._dialog_open or (
            self._installer is not None and self._installer.isRunning())

    def _install(self, info) -> None:
        if not info.asset_url:
            QMessageBox.information(
                self, "Update", "Im Release ist keine passende Programmdatei für dein System "
                "enthalten. Bitte lade die neue Version manuell von der Release-Seite herunter.")
            return
        progress = QProgressDialog("Update wird heruntergeladen …", "Abbrechen", 0, 100, self)
        progress.setWindowTitle("Update")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(False)

        self._installer = updater.UpdateInstaller(info.asset_url, info.hash_url, parent=self)
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
            return
        # apply returned False: in a real build that means the update could not be
        # applied automatically (on Windows e.g. the fail-closed signature check;
        # on macOS e.g. the bundle could not be swapped); in a dev run it is simply
        # not applicable.
        from app_meta import is_frozen
        if is_frozen():
            QMessageBox.warning(
                self, "Update nicht möglich",
                "Das Update konnte nicht automatisch angewendet werden (u. a. aus "
                "Sicherheitsgründen). Bitte lade die neue Version bei Bedarf manuell "
                "von der Release-Seite herunter.")
        else:
            QMessageBox.information(
                self, "Update", "Das Update wurde geladen. Im Entwicklungsmodus erfolgt kein "
                "automatischer Austausch – bitte die gebaute Programmversion verwenden.")

    def background_threads(self) -> list:
        """Running update threads owned by this view (for shutdown cleanup)."""
        return [self._checker, self._installer]

    # -- bank import management ---------------------------------------------
    def _import_card(self) -> QFrame:
        card, layout = self._card("Kontoauszug-Import")
        self._add_action_row(
            layout, "Kategorisierungs-Regeln verwalten (Empfänger → Kategorie)",
            "Regeln öffnen", self._open_rules, "Ghost")
        self._add_action_row(
            layout, "Gespeicherte Bank-Profile (CSV-Spalten) verwalten",
            "Profile öffnen", self._open_profiles, "Ghost")
        return card

    def _open_rules(self) -> None:
        from ui.bank_import_dialogs import ImportRulesDialog
        ImportRulesDialog(self.ctx.import_rules, self).exec()

    def _open_profiles(self) -> None:
        from ui.bank_import_dialogs import BankProfilesDialog
        BankProfilesDialog(self.ctx.bank_profiles, self).exec()

    # -- backups ------------------------------------------------------------
    def _backup_card(self) -> QFrame:
        card, layout = self._card("Datensicherung")
        self._add_action_row(layout, "Sicherungskopie der Datenbank erstellen",
                             "Backup erstellen", self._backup_now, "Ghost")
        self._add_action_row(layout, "Daten aus einer Sicherung wiederherstellen",
                             "Wiederherstellen …", self._restore_backup, "Ghost")
        self._add_action_row(layout, "Ordner mit den Sicherungen öffnen",
                             "Ordner öffnen",
                             lambda: self._open(backup.backups_dir(self.ctx.db.path)),
                             "Ghost")
        hint = QLabel(
            "Automatische Sicherungen: täglich beim Start sowie vor "
            "Kontoauszug-Import, Daten-Aktualisierung und Löschen. "
            f"Die letzten {backup.MAX_BACKUPS} Sicherungen werden aufbewahrt.")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _backup_now(self) -> None:
        try:
            path = backup.create_backup(
                self.ctx.db.conn, label="manuell",
                directory=backup.backups_dir(self.ctx.db.path))
        except backup.BackupError as exc:
            QMessageBox.warning(self, "Backup fehlgeschlagen", str(exc))
            return
        QMessageBox.information(
            self, "Backup erstellt",
            f"Die Sicherung wurde erstellt:\n{path.name}")

    def _restore_backup(self) -> None:
        backups = backup.list_backups(backup.backups_dir(self.ctx.db.path))
        if not backups:
            QMessageBox.information(
                self, "Keine Sicherungen",
                "Es sind noch keine Sicherungen vorhanden. Beim nächsten "
                "Programmstart wird automatisch eine erstellt.")
            return
        chosen = _RestoreDialog.pick(backups, self)
        if chosen is None:
            return
        # Never restore data written by a NEWER app version into this one.
        version = backup.backup_schema_version(chosen.path)
        if version is not None and version > CURRENT_SCHEMA_VERSION:
            QMessageBox.warning(
                self, "Wiederherstellung nicht möglich",
                "Diese Sicherung stammt von einer neueren Programmversion. "
                "Bitte aktualisiere zuerst den HaushaltsManager.")
            return
        stamp = chosen.created.strftime("%d.%m.%Y %H:%M")
        if QMessageBox.warning(
            self, "Wiederherstellen",
            f"Alle aktuellen Daten durch die Sicherung vom {stamp} ersetzen?\n"
            "Der jetzige Stand wird vorher automatisch gesichert.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            # Fail closed: without the safety snapshot of the CURRENT state,
            # no restore happens.
            backup.create_backup(
                self.ctx.db.conn, label="vor-wiederherstellung",
                directory=backup.backups_dir(self.ctx.db.path))
            backup.restore_into_connection(self.ctx.db.conn, chosen.path)
            self.ctx.db.reinitialise_after_restore()
        except backup.BackupError as exc:
            QMessageBox.warning(self, "Wiederherstellung fehlgeschlagen", str(exc))
            return
        self.ctx.notify_changed()
        QMessageBox.information(
            self, "Wiederhergestellt",
            f"Die Daten wurden auf den Stand vom {stamp} zurückgesetzt.")

    # -- app family -----------------------------------------------------------
    def _interop_card(self) -> QFrame:
        card, layout = self._card("App-Familie")
        # Kept as an attribute: refresh() re-reads ctx.sister so the periodic
        # family re-discovery is reflected without reopening the view.
        self._interop_status = QLabel(self.ctx.sister.message)
        self._interop_status.setWordWrap(True)
        layout.addWidget(self._interop_status)
        hint = QLabel(
            "Der HaushaltsManager stellt dem KFZ-Manager seine Monatsausgaben "
            "über eine schreibgeschützte Interop-Schicht bereit und zeigt "
            "dessen Fahrzeuge auf dem Dashboard — Fahrzeugkosten werden dabei "
            "nie doppelt gebucht, der KFZ-Manager bleibt die alleinige Quelle.")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    # -- data ---------------------------------------------------------------
    def _data_card(self) -> QFrame:
        card, layout = self._card("Daten")
        self._add_action_row(layout, "Quick-Setup-Wizard erneut starten",
                             "Assistent öffnen", lambda: run_wizard(self.ctx, self), "Primary")
        self._add_action_row(layout, "Speicherort der Daten öffnen",
                             "Ordner öffnen", lambda: self._open(data_dir()), "Ghost")
        self._add_action_row(layout, "Protokoll (Logdatei) öffnen",
                             "Protokoll öffnen", lambda: self._open(logs_dir()), "Ghost")
        self._add_action_row(layout, "Alle Finanzdaten unwiderruflich löschen",
                             "Alle Daten löschen", self._wipe_data, "Danger")
        return card

    def _add_action_row(self, layout, label: str, button_text: str, slot, kind: str) -> None:
        """One settings row: description left, fixed-width action button right.

        Built as a QHBoxLayout added via addLayout (not a wrapped QWidget) so the
        button keeps the card's full right margin and a uniform width — the cause
        of the previously clipped/inconsistent buttons.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(label))
        row.addStretch(1)
        btn = QPushButton(button_text)
        btn.setObjectName(kind)
        btn.setMinimumWidth(168)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        if kind == "Primary":
            # Inline fill (transparent scroll ancestor, see _sync_theme_buttons);
            # re-styled on theme change via _primary_row_btns.
            btn.setStyleSheet(primary_button_qss(self.ctx.colors))
            self._primary_row_btns.append(btn)
        row.addWidget(btn)
        layout.addLayout(row)

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
        # Fail closed: the reset is irreversible, so it only runs once a
        # snapshot of the current state exists.
        try:
            backup.create_backup(
                self.ctx.db.conn, label="vor-loeschen",
                directory=backup.backups_dir(self.ctx.db.path))
        except backup.BackupError as exc:
            QMessageBox.warning(
                self, "Löschen abgebrochen",
                "Vor dem Löschen konnte keine Sicherung erstellt werden - "
                f"es wurde nichts gelöscht.\n\n{exc}")
            return
        # Clears EVERY financial table (incl. one-off income, budgets, snapshots
        # and the bank-import log/rules) so no orphaned rows survive the reset.
        self.ctx.db.wipe_financial_data()
        self.ctx.notify_changed()
        QMessageBox.information(
            self, "Gelöscht",
            "Alle Finanzdaten wurden entfernt.\nEine Sicherung des vorherigen "
            "Stands liegt im Sicherungs-Ordner (Datensicherung).")

    @staticmethod
    def _open(path) -> None:
        platform_util.open_path(path)

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
        if hasattr(self, "_interop_status"):
            self._interop_status.setText(self.ctx.sister.message)

    def on_theme_changed(self) -> None:
        self._sync_theme_buttons()
        for btn in self._primary_row_btns:
            btn.setStyleSheet(primary_button_qss(self.ctx.colors))


class _RestoreDialog(QDialog):
    """Pick one backup from a list (newest first); returns the BackupInfo."""

    def __init__(self, backups, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sicherung wiederherstellen")
        self.setMinimumWidth(460)
        self._backups = backups
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Welche Sicherung soll wiederhergestellt werden?"))
        self._list = QListWidget()
        for info in backups:
            stamp = info.created.strftime("%d.%m.%Y %H:%M")
            size_mb = f"{info.size_bytes / 1_000_000:.1f}".replace(".", ",")
            QListWidgetItem(f"{stamp}  ·  {info.label_text}  ·  {size_mb} MB", self._list)
        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(lambda _i: self.accept())
        layout.addWidget(self._list)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        ok = QPushButton("Wiederherstellen")
        ok.setObjectName("Primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    @staticmethod
    def pick(backups, parent=None):
        dlg = _RestoreDialog(backups, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        row = dlg._list.currentRow()
        return backups[row] if 0 <= row < len(backups) else None

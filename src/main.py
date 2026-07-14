"""HaushaltsManager — application entry point.

Sets up logging and a friendly global exception handler, initialises the
database and configuration, applies the theme and shows the main window.
A headless smoke mode (HM_SMOKE=1) renders the window to a PNG and exits, so
the build can be verified without a human at the screen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# When run as a script, make the bundled ``src`` importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtGui import QIcon  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app_meta import APP_DISPLAY_NAME, APP_NAME, app_icon_path  # noqa: E402
from modules.config import Config  # noqa: E402
from modules.db_handler.database import Database  # noqa: E402
from modules.logging_setup import setup_logging  # noqa: E402
from ui import theme  # noqa: E402
from ui.app_context import AppContext  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def _set_app_user_model_id() -> None:
    """Give Windows an explicit AppUserModelID.

    Without this, a Python-hosted process inherits the interpreter's identity and
    the taskbar shows the wrong icon / fails to group windows. Must be set before
    any window is created.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"Mijonex.{APP_NAME}.App.1")
    except Exception:  # noqa: BLE001 - cosmetic only, never block startup
        pass


def main() -> int:
    log = setup_logging()
    log.info("Starte %s", APP_DISPLAY_NAME)

    _set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    icon_file = app_icon_path()
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    # Friendly catch-all: log the traceback, show a plain message, never crash
    # to a raw traceback in the user's face.
    def excepthook(exc_type, exc, tb):
        log.error("Unbehandelter Fehler", exc_info=(exc_type, exc, tb))
        try:
            QMessageBox.critical(
                None, APP_DISPLAY_NAME,
                "Ein unerwarteter Fehler ist aufgetreten.\n\n"
                f"{exc}\n\nDetails stehen im Protokoll (Einstellungen → Daten).",
            )
        except Exception:  # noqa: BLE001 - never let the handler itself crash
            pass

    sys.excepthook = excepthook

    try:
        db = _open_database()
        if db is None:
            return 1
        config = Config()
        from modules.seed import seed_if_empty
        if seed_if_empty(db):
            log.info("Datenbank mit Startdaten befüllt (erster Start).")
        # Automatic safety net: one snapshot per day, never blocks the start.
        from modules import backup
        backup.startup_backup(db.conn, backup.backups_dir(db.path))
        ctx = AppContext(db, config)
        # App family: announce ourselves and publish the expense contract for
        # the sister app (both fail silent — pure bonus features).
        from modules import interop
        interop.announce_self(db.path)
        interop.refresh_ausgaben_monat(db, ctx.fixed, ctx.expenses)
    except Exception as exc:  # noqa: BLE001
        log.exception("Start fehlgeschlagen")
        QMessageBox.critical(None, APP_DISPLAY_NAME, f"Start fehlgeschlagen:\n{exc}")
        return 1

    # Optional theme override for testing/screenshots (does not persist).
    if os.environ.get("HM_THEME") in ("light", "dark"):
        ctx.config._data["theme"] = os.environ["HM_THEME"]

    app.setStyleSheet(theme.build_qss(ctx.colors))
    window = MainWindow(ctx)
    window.show()

    # Optional first-run seeding and update check are wired up here later.
    _maybe_first_run(ctx, window)

    if os.environ.get("HM_SMOKE"):
        view_index = int(os.environ.get("HM_VIEW", "0"))
        window._select(view_index)

        def _smoke() -> None:
            shot = os.environ.get("HM_SHOT")
            if shot:
                window.grab().save(shot)
                log.info("Smoke-Screenshot gespeichert: %s", shot)
            app.quit()
        QTimer.singleShot(1500, _smoke)

    return app.exec()


def _open_database() -> Database | None:
    """Open the database; on corruption offer to restore the newest backup.

    Returns None when the app cannot continue (user declined or recovery
    failed) — the caller shows no further message in that case, every path
    here already told the user what happened.
    """
    from app_meta import database_path
    from modules import backup
    from modules.db_handler.database import DatabaseCorruptError

    try:
        return Database()
    except DatabaseCorruptError:
        backups = backup.list_backups(backup.backups_dir(database_path()))
        if not backups:
            QMessageBox.critical(
                None, APP_DISPLAY_NAME,
                "Die Datenbank ist beschädigt und kann nicht geöffnet werden.\n\n"
                "Es ist keine Sicherung vorhanden. Wenn du die Datei "
                f"{database_path().name} umbenennst, startet das Programm mit "
                "einer leeren Datenbank.")
            return None
        newest = backups[0]
        stamp = newest.created.strftime("%d.%m.%Y %H:%M")
        choice = QMessageBox.warning(
            None, APP_DISPLAY_NAME,
            "Die Datenbank ist beschädigt und kann nicht geöffnet werden.\n\n"
            f"Jüngste Sicherung: {stamp} ({newest.label_text}).\n"
            "Soll diese Sicherung wiederhergestellt werden? Die beschädigte "
            "Datei wird nicht gelöscht, sondern umbenannt.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if choice != QMessageBox.StandardButton.Yes:
            return None
        try:
            backup.replace_database_file(database_path(), newest.path)
            return Database()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                None, APP_DISPLAY_NAME,
                f"Die Wiederherstellung ist fehlgeschlagen:\n{exc}")
            return None


def _maybe_first_run(ctx: AppContext, window: MainWindow) -> None:
    """Run the first-time wizard if needed and kick off the update check.

    Skipped entirely in headless smoke mode so automated runs never block.
    """
    if os.environ.get("HM_SMOKE"):
        return
    from modules.seed import database_is_empty
    from ui.wizard import run_wizard

    if not ctx.config.get("wizard_completed") and database_is_empty(ctx.db):
        run_wizard(ctx, window)
        window._refresh_current()

    window.maybe_check_updates()


if __name__ == "__main__":
    sys.exit(main())

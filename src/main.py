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
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app_meta import APP_DISPLAY_NAME  # noqa: E402
from modules.config import Config  # noqa: E402
from modules.db_handler.database import Database  # noqa: E402
from modules.logging_setup import setup_logging  # noqa: E402
from ui import theme  # noqa: E402
from ui.app_context import AppContext  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    log = setup_logging()
    log.info("Starte %s", APP_DISPLAY_NAME)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)

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
        db = Database()
        config = Config()
        from modules.seed import seed_if_empty
        if seed_if_empty(db):
            log.info("Datenbank mit Startdaten befüllt (erster Start).")
        ctx = AppContext(db, config)
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

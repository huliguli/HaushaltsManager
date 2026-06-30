"""Headless UI smoke test.

The rest of the suite covers pure logic but never constructs a widget, so an
ImportError, a missing colour token, a broken icon or a QSS typo would only
surface as a start-up crash for the user while the suite stays green. This test
builds the whole window, visits every view (running each refresh()) and toggles
the theme — under the offscreen Qt platform so it runs without a display/CI.
"""

import os

# Must be set before the first QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_mainwindow_and_all_views_construct(tmp_path, monkeypatch):
    # Isolate config from the real %APPDATA% so the test never touches user prefs.
    monkeypatch.setenv("APPDATA", str(tmp_path))

    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable in this env
        import pytest
        pytest.skip(f"Qt nicht verfügbar: {exc}")

    from modules.config import Config
    from modules.db_handler.database import Database
    from ui import theme
    from ui.app_context import AppContext
    from ui.main_window import _NAV, MainWindow

    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / "smoke.db")
    ctx = AppContext(db, Config())
    app.setStyleSheet(theme.build_qss(ctx.colors))

    window = MainWindow(ctx)
    # Visiting each view runs its refresh()/build path (incl. the donut chart).
    # Iterate the real navigation length so a future 7th view is covered too.
    for index in range(len(_NAV)):
        window._select(index)
    # Toggling the theme rebuilds the QSS and re-tints/refreshes every view.
    ctx.set_theme("dark")
    ctx.set_theme("light")

    window.close()
    db.close()

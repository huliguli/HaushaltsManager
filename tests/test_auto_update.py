"""Widget tests for the startup auto-update routing (offscreen Qt platform).

Pins the opt-in contract: default = confirmation dialog, with
``update_auto_install`` = direct install; a skipped version and an update
info without an asset never reach the auto path.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Keep the QApplication referenced for the whole module lifetime (see
# test_drilldown.py: an unreferenced instance segfaults on teardown).
_APP = None


def _window(tmp_path, monkeypatch):
    global _APP
    monkeypatch.setenv("APPDATA", str(tmp_path))
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable in this env
        import pytest
        pytest.skip(f"Qt nicht verfügbar: {exc}")
    _APP = QApplication.instance() or QApplication([])

    from modules.config import Config
    from modules.db_handler.database import Database
    from ui import theme
    from ui.app_context import AppContext
    from ui.main_window import MainWindow

    db = Database(tmp_path / "upd.db")
    ctx = AppContext(db, Config())
    _APP.setStyleSheet(theme.build_qss(ctx.colors))
    return MainWindow(ctx), ctx, db


def _info(asset: str = "https://github.com/x/Setup.exe"):
    from modules.updater.updater import UpdateInfo
    return UpdateInfo(version="99.0.0", tag="v99.0.0", notes="",
                      asset_url=asset, html_url="https://github.com/x")


def _spy(window):
    """Replace the settings view's two entry points with recorders."""
    calls = []
    settings = window._views[-1]
    settings.auto_install = lambda info: calls.append(("auto", info.tag))
    settings.show_update_dialog = lambda info: calls.append(("dialog", info.tag))
    return calls


def test_default_asks_via_dialog(tmp_path, monkeypatch):
    window, ctx, db = _window(tmp_path, monkeypatch)
    calls = _spy(window)
    window._on_startup_update(_info())
    assert calls == [("dialog", "v99.0.0")]
    window.close()
    db.close()


def test_opt_in_installs_without_asking(tmp_path, monkeypatch):
    window, ctx, db = _window(tmp_path, monkeypatch)
    ctx.config.set("update_auto_install", True)
    calls = _spy(window)
    window._on_startup_update(_info())
    assert calls == [("auto", "v99.0.0")]
    window.close()
    db.close()


def test_auto_path_needs_an_asset_and_respects_skip(tmp_path, monkeypatch):
    window, ctx, db = _window(tmp_path, monkeypatch)
    ctx.config.set("update_auto_install", True)
    calls = _spy(window)
    # No platform asset -> never auto-run; fall back to the dialog flow
    # (which shows the manual-download hint on install).
    window._on_startup_update(_info(asset=""))
    assert calls == [("dialog", "v99.0.0")]
    # A version the user skipped earlier stays skipped, auto or not.
    ctx.config.set("skipped_version", "v99.0.0")
    calls.clear()
    window._on_startup_update(_info())
    assert calls == []
    window.close()
    db.close()

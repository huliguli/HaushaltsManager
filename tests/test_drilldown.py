"""Widget tests for the chart drilldown (offscreen Qt platform).

Covers the wiring end to end: ``ctx.request_drilldown`` must switch the main
window to the Haushaltsbuch, open the expenses tab and apply month + category —
plus the expenses-tab scope rules (search widens to all months, drilldown and
Zurücksetzen return to the month scope).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Keep the QApplication referenced for the whole module lifetime: an
# unreferenced instance gets garbage-collected while widgets still exist,
# which crashes the interpreter (segfault, not a test failure).
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
    from modules.models import VariableExpense
    from ui import theme
    from ui.app_context import AppContext
    from ui.main_window import MainWindow

    db = Database(tmp_path / "drill.db")
    ctx = AppContext(db, Config())
    _APP.setStyleSheet(theme.build_qss(ctx.colors))
    ctx.expenses.add(VariableExpense("2026-05-04", 3_000, "Lebensmittel", "Edeka"))
    ctx.expenses.add(VariableExpense("2026-05-10", 4_500, "Auto & Tanken", "Aral"))
    ctx.expenses.add(VariableExpense("2026-06-01", 2_000, "Lebensmittel", "Rewe"))
    return MainWindow(ctx), ctx, db


def test_drilldown_opens_filtered_expenses(tmp_path, monkeypatch):
    window, ctx, db = _window(tmp_path, monkeypatch)
    from ui.views.haushaltsbuch_view import HaushaltsbuchView

    ctx.request_drilldown(2026, 5, "Lebensmittel")

    view = window._views[window._stack.currentIndex()]
    assert isinstance(view, HaushaltsbuchView)
    tab = view.expenses_tab
    assert view.tabs.currentWidget() is tab
    assert (tab._year, tab._month) == (2026, 5)
    assert tab.scope.currentData() == "month"
    assert tab.cat_filter.currentData() == "Lebensmittel"
    # Exactly the May grocery booking is shown (June + other category filtered out).
    assert tab.table.rowCount() == 1
    assert tab.table.item(0, 2).text() == "Edeka"

    window.close()
    db.close()


def test_drilldown_without_category_shows_whole_month(tmp_path, monkeypatch):
    window, ctx, db = _window(tmp_path, monkeypatch)
    ctx.request_drilldown(2026, 5, "")
    tab = window._views[window._stack.currentIndex()].expenses_tab
    assert tab.cat_filter.currentData() is None
    assert tab.table.rowCount() == 2                    # both May bookings
    # An unknown category falls back to "Alle Kategorien" but keeps the month.
    ctx.request_drilldown(2026, 6, "Gibt es nicht")
    assert tab.cat_filter.currentData() is None
    assert (tab._year, tab._month) == (2026, 6)
    assert tab.table.rowCount() == 1
    window.close()
    db.close()


def test_search_widens_scope_and_reset_restores_month(tmp_path, monkeypatch):
    window, ctx, db = _window(tmp_path, monkeypatch)
    ctx.request_drilldown(2026, 5, "")
    tab = window._views[window._stack.currentIndex()].expenses_tab

    # Typing a search auto-switches to the all-months scope (cross-month search).
    tab.search.setText("rewe")
    assert tab.scope.currentData() == "all"
    assert tab.table.rowCount() == 1                    # June match found
    assert not tab._nav.isEnabled()

    # Zurücksetzen returns to the plain month view.
    tab._reset_filters()
    assert tab.scope.currentData() == "month"
    assert tab.search.text() == ""
    assert tab.table.rowCount() == 2                    # May view again
    assert tab._nav.isEnabled()
    window.close()
    db.close()

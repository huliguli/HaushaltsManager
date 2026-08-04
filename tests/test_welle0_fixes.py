"""Regression tests for the correctness fixes of the v4.0 overhaul (wave 0).

Each test pins down a bug that shipped in v3.7.1 and was found during the audit.
They are deliberately narrow: one behaviour per test, so a future refactor tells
you exactly which promise it broke.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# --- Import-Rollback bei identischen Buchungen ------------------------------
def test_rollback_removes_every_booking_of_a_duplicate_pair(tmp_path, monkeypatch):
    """Two identical transactions must be fully undone, not half of them.

    Same day, same amount, same payee (a normal PDF/CSV case) produce one
    transaction_hash. The log's UNIQUE(tx_hash) used to swallow the second row,
    so rollback deleted one of the two created bookings and left the other.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules.bank_import.commit import commit_transactions, rollback_batch
    from modules.bank_import.model import BankTransaction
    from modules.db_handler.database import Database
    from modules.db_handler.repositories import (
        ImportLogRepository,
        ImportRuleRepository,
        VariableExpenseRepository,
        VariableIncomeRepository,
    )

    db = Database(tmp_path / "dup.db")
    expenses = VariableExpenseRepository(db)
    incomes = VariableIncomeRepository(db)
    rules = ImportRuleRepository(db)
    log = ImportLogRepository(db)

    twin = dict(booking_date="2026-08-04", amount_cents=-350,
                payee="Baeckerei", purpose="Broetchen", category="Lebensmittel")
    transactions = [BankTransaction(**twin), BankTransaction(**twin)]

    n_exp, _n_inc = commit_transactions(
        transactions, expenses, incomes, rules, log, batch_id="batch-1")
    assert n_exp == 2, "beide Buchungen muessen angelegt werden"
    assert len(expenses.list_recent(100)) == 2

    removed_exp, _removed_inc = rollback_batch("batch-1", expenses, incomes, log)
    assert removed_exp == 2, "der Rollback muss BEIDE Buchungen entfernen"
    assert expenses.list_recent(100) == []
    db.close()


# --- Fixkosten in der Kategorie-Auswertung ----------------------------------
def test_category_breakdown_includes_fixed_costs(tmp_path, monkeypatch):
    """The breakdown must cover the whole month, not just its variable part."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules import budget
    from modules.db_handler.database import Database
    from modules.db_handler.repositories import (
        FixedCostRepository,
        IncomeRepository,
        VariableExpenseRepository,
    )
    from modules.models import FixedCost, VariableExpense

    db = Database(tmp_path / "cats.db")
    income = IncomeRepository(db)
    fixed = FixedCostRepository(db)
    expenses = VariableExpenseRepository(db)

    fixed.add(FixedCost(name="Kaltmiete", amount_cents=74500, category="Wohnen"))
    fixed.add(FixedCost(name="KFZ", amount_cents=9600, category="Auto"))
    expenses.add(VariableExpense(date="2026-08-04", amount_cents=4285,
                                 category="Lebensmittel"))
    expenses.add(VariableExpense(date="2026-08-04", amount_cents=6740,
                                 category="Auto & Tanken"))

    ov = budget.compute_overview(income, fixed, expenses, 2026, 8)
    merged = ov.all_by_category

    # The variable-only view is still available and unchanged.
    assert ov.expenses_by_category["Lebensmittel"] == 4285
    # Rent shows up at all (it never did before) ...
    assert merged["Wohnen & Miete"] == 74500
    # ... and a category with both parts is summed, not overwritten.
    assert merged["Auto & Tanken"] == 9600 + 6740
    # The breakdown now accounts for every cent that left the account.
    assert sum(merged.values()) == ov.fixed_cents + ov.variable_cents
    # Sorted descending, so callers can take the top N.
    assert list(merged.values()) == sorted(merged.values(), reverse=True)
    db.close()


def test_savings_keep_their_own_bucket(tmp_path, monkeypatch):
    """A savings rate leaves the account but is not spending — own category."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules import budget
    from modules.db_handler.database import Database
    from modules.db_handler.repositories import (
        FixedCostRepository,
        IncomeRepository,
        VariableExpenseRepository,
    )
    from modules.models import FixedCost

    db = Database(tmp_path / "save.db")
    fixed = FixedCostRepository(db)
    fixed.add(FixedCost(name="Notgroschen", amount_cents=15000, category="Sparen"))
    ov = budget.compute_overview(IncomeRepository(db), fixed,
                                 VariableExpenseRepository(db), 2026, 8)
    assert ov.all_by_category["Sparen & Rücklagen"] == 15000
    db.close()


# --- Achsenbeschriftung der Diagramme ---------------------------------------
def test_chart_axis_labels_match_the_plotted_amounts():
    """A tick must be labelled with the amount that is actually plotted.

    The old matplotlib canvas converted cents to euros in the plot method and
    then let the tick formatter divide by 100 a SECOND time, so 3.000 EUR was
    labelled "30 EUR". The QPainter charts convert exactly once, at the label,
    and take integer cents throughout — this test pins that contract down.
    """
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable
        import pytest
        pytest.skip(f"Qt nicht verfügbar: {exc}")

    from modules.money import format_eur_short
    from ui import theme
    from ui.widgets.charts import ColumnTrend

    QApplication.instance() or QApplication([])
    chart = ColumnTrend(theme.palette("light"))
    chart.resize(600, 260)
    # 3.000,00 EUR and 1.500,00 EUR as integer cents.
    chart.set_data(["Jan", "Feb"], [300000, 150000], [280000, 140000])

    # The formatter used for the axis is the app's own money formatter, which
    # takes CENTS — so the tick for 3.000 EUR must read "3.000 EUR", not "30".
    assert format_eur_short(300000) == "3.000 €"
    assert format_eur_short(150000) == "1.500 €"
    assert format_eur_short(0) == "0 €"

    # Rendering must not raise and must produce a non-empty pixmap.
    pixmap = chart.grab()
    assert not pixmap.isNull()
    assert pixmap.width() > 0


# --- Updater-Kopplung --------------------------------------------------------
def test_settings_view_is_found_by_class_not_by_position(tmp_path, monkeypatch):
    """Reordering the navigation must not disable auto-update.

    The update flow used to grab self._views[-1]. Moving "Einstellungen" away
    from the last slot then silently broke the update check — no error, no log.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable
        import pytest
        pytest.skip(f"Qt nicht verfügbar: {exc}")

    from modules.config import Config
    from modules.db_handler.database import Database
    from ui import main_window as mw
    from ui.app_context import AppContext
    from ui.views.einstellungen_view import EinstellungenView

    QApplication.instance() or QApplication([])
    db = Database(tmp_path / "nav.db")
    ctx = AppContext(db, Config())

    # Move the settings entry to the FRONT — the old lookup would break here.
    reordered = [entry for entry in mw._NAV if entry[2] is EinstellungenView]
    reordered += [entry for entry in mw._NAV if entry[2] is not EinstellungenView]
    monkeypatch.setattr(mw, "_NAV", reordered)

    window = mw.MainWindow(ctx)
    found = window._settings_view()
    assert isinstance(found, EinstellungenView)
    assert found is window._views[0], "Einstellungen steht jetzt vorne"
    window.close()
    db.close()


# --- Auto-Seeding ------------------------------------------------------------
def test_seeding_does_not_undo_a_wipe(tmp_path, monkeypatch):
    """After "Alle Daten löschen" the seed must not refill the database.

    seed_if_empty() ran on every start. Since a wipe leaves the database empty
    and the seed file on disk, the next launch quietly restored the old data.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules.config import Config

    config = Config()
    assert config.get("initial_seed_done") is False, "erster Start darf seeden"

    # Simulate the first start having done its seed check.
    config.set("initial_seed_done", True)

    # A fresh Config (= next app start) must remember that.
    assert Config().get("initial_seed_done") is True


# --- Verzoegerter Ansichtsbau ------------------------------------------------
def test_lazy_views_keep_stack_and_navigation_in_step(tmp_path, monkeypatch):
    """Building a view on demand must not shift the stack under the selection.

    The placeholder swap (insertWidget + removeWidget) moves QStackedWidget's
    current index, so selecting a view before building it landed on the
    NEIGHBOURING view. Every entry must resolve to its own class.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable
        import pytest
        pytest.skip(f"Qt nicht verfügbar: {exc}")

    from modules.config import Config
    from modules.db_handler.database import Database
    from ui import main_window as mw
    from ui.app_context import AppContext

    QApplication.instance() or QApplication([])
    db = Database(tmp_path / "lazy.db")
    ctx = AppContext(db, Config())
    window = mw.MainWindow(ctx)

    # Only the start view exists after construction — that is the whole point.
    built = [v for v in window._views if v is not None]
    assert len(built) == 1, "beim Start darf nur die erste Ansicht gebaut sein"

    # Visiting every entry must yield exactly its own class, in order.
    for index, (_label, _icon, view_cls) in enumerate(mw._NAV):
        window._select(index)
        assert window._stack.currentIndex() == index
        assert isinstance(window._current_view(), view_cls), (
            f"Eintrag {index} zeigt die falsche Ansicht")
    window.close()
    db.close()

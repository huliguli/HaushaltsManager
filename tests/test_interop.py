"""App-Familie (schema v7): Ankündigung, Ausgaben-Contract, Schwester-Lesen.

Simuliert den KFZ-Manager über echte Dateien in einem per-Test umgeleiteten
APPDATA — exakt das Produktionslayout (Familienordner + read-only-DB).
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from modules import interop
from modules.db_handler.database import (
    CURRENT_SCHEMA_VERSION,
    INTEROP_VERSION,
    Database,
)
from modules.db_handler.repositories import (
    FixedCostRepository,
    VariableExpenseRepository,
)
from modules.models import FixedCost, VariableExpense

TODAY = date(2026, 7, 14)


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    yield


def _family_dir():
    from app_meta import family_dir
    return family_dir()


def _announce_sister(db_path: Path, interop_version: int = INTEROP_VERSION,
                     app_version: str = "1.0.0") -> Path:
    payload = {
        "app_name": "KFZManager",
        "app_version": app_version,
        "interop_version": interop_version,
        "db_path": str(db_path),
        "updated_at": "2026-07-14T00:00:00+00:00",
    }
    target = _family_dir() / interop.SISTER_ANNOUNCE_FILE
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _sister_db(tmp_path: Path) -> Path:
    """Minimal KFZ-Manager database exposing the v1 interop contract.

    Views are modelled as plain tables — for the reader the access is
    identical, and it keeps the fixture free of the sister's schema.
    """
    path = tmp_path / "kfz.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE interop_meta (interop_version INTEGER NOT NULL)")
    conn.execute("INSERT INTO interop_meta VALUES (?)", (INTEROP_VERSION,))
    conn.execute("CREATE TABLE interop_fahrzeuge (id INTEGER, name TEXT, antrieb TEXT)")
    conn.executemany("INSERT INTO interop_fahrzeuge VALUES (?, ?, ?)",
                     [(1, "Golf", "diesel"), (2, "Zoe", "elektro")])
    conn.execute("CREATE TABLE interop_kosten_monat "
                 "(fahrzeug_id INTEGER, jahr INTEGER, monat INTEGER, "
                 " kategorie TEXT, betrag_cent INTEGER)")
    conn.executemany(
        "INSERT INTO interop_kosten_monat VALUES (?, ?, ?, ?, ?)",
        [(1, 2026, 7, "Werkstatt", 12000), (1, 2026, 7, "Kraftstoff/Strom", 8000),
         (2, 2026, 7, "Versicherung", 4000), (1, 2026, 6, "Pflege", 999)])
    conn.execute("CREATE TABLE interop_termine "
                 "(fahrzeug_id INTEGER, typ TEXT, faellig_datum TEXT, "
                 " faellig_km INTEGER, beschreibung TEXT)")
    conn.executemany(
        "INSERT INTO interop_termine VALUES (?, ?, ?, ?, ?)",
        [(1, "TÜV/HU", "2026-09-01", None, "Hauptuntersuchung"),
         (2, "Inspektion", None, 30000, "Jahresinspektion"),
         (1, "Reifenwechsel", "2026-10-15", None, "Winterreifen")])
    conn.commit()
    conn.close()
    return path


# --- schema v7 -----------------------------------------------------------------
def test_fresh_db_has_v7_and_interop_meta(tmp_path):
    db = Database(tmp_path / "t.db")
    try:
        assert db.query_one("SELECT version FROM schema_version")["version"] \
            == CURRENT_SCHEMA_VERSION == 7
        assert db.query_one(
            "SELECT interop_version FROM interop_meta")["interop_version"] \
            == INTEROP_VERSION
    finally:
        db.close()


def test_v6_database_is_lifted_to_v7(tmp_path):
    path = tmp_path / "t.db"
    db = Database(path)
    # Simulate a database written by v3.5: no interop tables, version 6.
    db.conn.execute("DROP TABLE interop_ausgaben_monat")
    db.conn.execute("DROP TABLE interop_meta")
    db.conn.execute("UPDATE schema_version SET version = 6")
    db.conn.commit()
    db.close()
    db2 = Database(path)
    try:
        assert db2.query_one("SELECT version FROM schema_version")["version"] == 7
        assert db2.query_one("SELECT interop_version FROM interop_meta") is not None
    finally:
        db2.close()


# --- announcement ------------------------------------------------------------------
def test_announce_self_writes_json(tmp_path):
    interop.announce_self(tmp_path / "haushalt.db")
    data = json.loads(
        (_family_dir() / interop.OWN_ANNOUNCE_FILE).read_text("utf-8"))
    assert data["app_name"] == "HaushaltsManager"
    assert data["interop_version"] == INTEROP_VERSION
    assert data["db_path"].endswith("haushalt.db")


# --- expense contract -----------------------------------------------------------------
def test_refresh_ausgaben_monat_sums_fixed_and_variable(tmp_path):
    db = Database(tmp_path / "t.db")
    try:
        fixed = FixedCostRepository(db)
        expenses = VariableExpenseRepository(db)
        fixed.add(FixedCost(name="Miete", amount_cents=78_000))
        expenses.add(VariableExpense(date="2026-07-05", amount_cents=6_150,
                                     category="Lebensmittel"))
        # Recurring template from March: counts in July too.
        expenses.add(VariableExpense(date="2026-03-10", amount_cents=1_999,
                                     category="Streaming & Abos", recurring=True))

        rows = interop.refresh_ausgaben_monat(db, fixed, expenses, today=TODAY)
        assert rows == interop.MONTHS_BACK + 1

        row = db.query_one(
            "SELECT summe_cent FROM interop_ausgaben_monat WHERE jahr=? AND monat=?",
            (2026, 7))
        assert row["summe_cent"] == 78_000 + 6_150 + 1_999
        # March carries fixed + first recurring occurrence, no groceries.
        row3 = db.query_one(
            "SELECT summe_cent FROM interop_ausgaben_monat WHERE jahr=? AND monat=?",
            (2026, 3))
        assert row3["summe_cent"] == 78_000 + 1_999
    finally:
        db.close()


def test_refresh_is_full_rebuild(tmp_path):
    db = Database(tmp_path / "t.db")
    try:
        fixed = FixedCostRepository(db)
        expenses = VariableExpenseRepository(db)
        eid = expenses.add(VariableExpense(date="2026-07-05", amount_cents=5_000,
                                           category="Sonstiges"))
        interop.refresh_ausgaben_monat(db, fixed, expenses, today=TODAY)
        expenses.delete(eid)
        interop.refresh_ausgaben_monat(db, fixed, expenses, today=TODAY)
        row = db.query_one(
            "SELECT summe_cent FROM interop_ausgaben_monat WHERE jahr=? AND monat=?",
            (2026, 7))
        assert row["summe_cent"] == 0
    finally:
        db.close()


def test_wipe_clears_contract_table(tmp_path):
    db = Database(tmp_path / "t.db")
    try:
        fixed = FixedCostRepository(db)
        expenses = VariableExpenseRepository(db)
        interop.refresh_ausgaben_monat(db, fixed, expenses, today=TODAY)
        assert db.query("SELECT * FROM interop_ausgaben_monat")
        db.wipe_financial_data()
        assert db.query("SELECT * FROM interop_ausgaben_monat") == []
    finally:
        db.close()


# --- discovery / handshake ---------------------------------------------------------------
def test_discover_missing_sister():
    assert interop.discover_sister().status == "fehlt"


def test_discover_broken_json():
    (_family_dir() / interop.SISTER_ANNOUNCE_FILE).write_text("{kaputt", "utf-8")
    assert interop.discover_sister().status == "fehler"


def test_discover_version_mismatch(tmp_path):
    _announce_sister(_sister_db(tmp_path), interop_version=INTEROP_VERSION + 1)
    state = interop.discover_sister()
    assert state.status == "version"
    assert "aktualisieren" in state.message


def test_discover_active(tmp_path):
    db_path = _sister_db(tmp_path)
    _announce_sister(db_path)
    state = interop.discover_sister()
    assert state.status == "aktiv" and state.db_path == db_path


def test_discover_missing_db(tmp_path):
    _announce_sister(tmp_path / "fehlt.db")
    assert interop.discover_sister().status == "fehler"


# --- reading the sister ------------------------------------------------------------------
def test_sister_vehicles_and_costs(tmp_path):
    db_path = _sister_db(tmp_path)
    vehicles = interop.sister_vehicles(db_path)
    assert [v.name for v in vehicles] == ["Golf", "Zoe"]
    costs = interop.vehicle_month_costs(db_path, 2026, 7)
    assert costs == {1: 20_000, 2: 4_000}  # categories aggregated per vehicle
    assert interop.vehicle_month_costs(db_path, 2025, 1) == {}


def test_next_appointments_sorted_dated_first(tmp_path):
    appts = interop.next_appointments(_sister_db(tmp_path))
    assert [a.typ for a in appts] == ["TÜV/HU", "Reifenwechsel", "Inspektion"]
    assert appts[2].faellig_km == 30_000


def test_unreadable_sister_degrades_silently(tmp_path):
    fake = tmp_path / "kfz.db"
    fake.write_bytes(b"keine datenbank")
    assert interop.sister_vehicles(fake) == []
    assert interop.vehicle_month_costs(fake, 2026, 7) == {}
    assert interop.next_appointments(fake) == []


def test_refresh_sister_detects_change(tmp_path):
    # Non-Qt: the context helper used by the 5-minute family timer.
    from modules.config import Config  # noqa: F401 - ensure importable env
    state_before = interop.discover_sister()
    assert state_before.status == "fehlt"
    _announce_sister(_sister_db(tmp_path))
    state_after = interop.discover_sister()
    assert state_after.status == "aktiv"


# --- dashboard card (offscreen Qt) ----------------------------------------------------
_APP = None  # keep the QApplication referenced (see test_drilldown.py)


def test_dashboard_shows_vehicle_card_when_sister_active(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    global _APP
    try:
        from PyQt6.QtWidgets import QApplication, QLabel
    except Exception as exc:  # pragma: no cover - Qt unavailable in this env
        pytest.skip(f"Qt nicht verfügbar: {exc}")
    _APP = QApplication.instance() or QApplication([])

    # Sister present BEFORE the context discovers it.
    _announce_sister(_sister_db(tmp_path))

    from modules.config import Config
    from ui.app_context import AppContext
    from ui.views.dashboard_view import DashboardView

    db = Database(tmp_path / "t.db")
    try:
        ctx = AppContext(db, Config())
        assert ctx.sister.status == "aktiv"
        view = DashboardView(ctx)
        view.refresh()
        texts = [w.text() for w in view.findChildren(QLabel)]
        assert any("Fahrzeuge (KFZ-Manager)" in t for t in texts)
        assert any("Golf" in t for t in texts)
    finally:
        db.close()


def test_family_tick_picks_up_new_sister_live(tmp_path, monkeypatch):
    """The 5-minute timer must surface a sister installed AFTER app start."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    global _APP
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable in this env
        pytest.skip(f"Qt nicht verfügbar: {exc}")
    _APP = QApplication.instance() or QApplication([])

    from modules.config import Config
    from ui.app_context import AppContext
    from ui.main_window import MainWindow

    db = Database(tmp_path / "t.db")
    try:
        ctx = AppContext(db, Config())
        window = MainWindow(ctx)
        assert ctx.sister.status == "fehlt"
        # Sister appears while we are running...
        _announce_sister(_sister_db(tmp_path))
        window._family_tick()
        assert ctx.sister.status == "aktiv"
        # ...and our own announcement was refreshed by the tick.
        assert (_family_dir() / interop.OWN_ANNOUNCE_FILE).is_file()
        window.close()
    finally:
        db.close()


def test_dashboard_without_sister_has_no_vehicle_card(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    global _APP
    try:
        from PyQt6.QtWidgets import QApplication, QLabel
    except Exception as exc:  # pragma: no cover - Qt unavailable in this env
        pytest.skip(f"Qt nicht verfügbar: {exc}")
    _APP = QApplication.instance() or QApplication([])

    from modules.config import Config
    from ui.app_context import AppContext
    from ui.views.dashboard_view import DashboardView

    db = Database(tmp_path / "t.db")
    try:
        ctx = AppContext(db, Config())
        view = DashboardView(ctx)
        view.refresh()
        texts = [w.text() for w in view.findChildren(QLabel)]
        assert not any("Fahrzeuge (KFZ-Manager)" in t for t in texts)
    finally:
        db.close()

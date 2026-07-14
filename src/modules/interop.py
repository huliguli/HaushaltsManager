"""App-family interop: announce this app, provide the expense contract and
read the sister app's (KFZ-Manager) interop views.

The contract (full spec: INTEROP.md in the KFZ-Manager repository):

    * Every family app writes an announcement file into the shared family
      folder (``<data base>/AppFamilie``) on each start:
      ``haushaltsmanager.json`` / ``kfzmanager.json`` with
      ``{app_name, app_version, interop_version, db_path, updated_at}``.
    * This app provides ``interop_meta`` (version handshake) and
      ``interop_ausgaben_monat (jahr, monat, summe_cent)`` — the total
      household expenses per month. Because that figure needs the
      recurring-expense materialisation and fixed-cost date logic that live
      in Python, the table is MATERIALISED here (rebuilt at startup and on
      every data change) rather than a SQL view; for the reader the access
      is identical.
    * A sister database is read EXCLUSIVELY through its ``interop_*`` views
      plus ``interop_meta`` — never through private tables — and strictly
      read-only (``file:…?mode=ro`` + busy_timeout).
    * Handshake: integration only when both sides carry the same
      interop_version major; otherwise a polite "bitte <App> aktualisieren"
      hint and the integration stays off.

Failure philosophy: the integration is a bonus. Every error path (missing
folder, broken JSON, locked/missing DB, the WAL read-only edge case where a
WAL-mode database cannot be opened read-only) degrades to "integration off
for this session" — it NEVER crashes or blocks the app.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app_meta import APP_VERSION, database_path, family_dir
from modules import dates
from modules.db_handler.database import INTEROP_VERSION
from modules.logging_setup import get_logger

_log = get_logger("interop")

OWN_ANNOUNCE_FILE = "haushaltsmanager.json"
SISTER_ANNOUNCE_FILE = "kfzmanager.json"
SISTER_APP_NAME = "KFZ-Manager"

# How far back the materialised expense history reaches. 48 months covers
# every realistic budget comparison; the sister recomputes percentages only
# for recent months anyway, and the table stays tiny.
MONTHS_BACK = 48


@dataclass(frozen=True)
class SisterState:
    """Result of the discovery/handshake for the settings/dashboard UI."""
    status: str          # 'aktiv' | 'fehlt' | 'version' | 'fehler'
    message: str         # German status text
    db_path: Path | None = None
    app_version: str = ""
    interop_version: int | None = None


@dataclass(frozen=True)
class SisterVehicle:
    id: int
    name: str
    antrieb: str


@dataclass(frozen=True)
class SisterAppointment:
    fahrzeug_id: int
    typ: str
    faellig_datum: str | None   # ISO
    faellig_km: int | None
    beschreibung: str


def announce_self(db_path: Path | None = None, now: datetime | None = None) -> None:
    """Write/refresh our announcement file in the family folder.

    Called on every start. Never raises — a read-only profile or exotic
    setup must not break the app over a bonus feature.
    """
    try:
        payload = {
            "app_name": "HaushaltsManager",
            "app_version": APP_VERSION,
            "interop_version": INTEROP_VERSION,
            "db_path": str(db_path or database_path()),
            "updated_at": (now or datetime.now(timezone.utc)).isoformat(),
        }
        target = family_dir() / OWN_ANNOUNCE_FILE
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Familien-Ankündigung fehlgeschlagen: %s", exc)


def refresh_ausgaben_monat(db, fixed_repo, expense_repo,
                           today=None, months_back: int = MONTHS_BACK) -> int:
    """Rebuild ``interop_ausgaben_monat`` from the live data (full rewrite).

    One row per month from ``months_back`` months ago through the current
    month: ``summe_cent`` = fixed costs effective that month + variable
    expenses (incl. materialised recurring occurrences) — exactly the two
    spending blocks of the dashboard overview. A full rebuild keeps the
    table trivially consistent after edits, imports, restores and wipes.
    Returns the number of rows written. Never raises (bonus feature).
    """
    from modules.budget import month_bounds

    try:
        today = today or dates.today()
        year, month = dates.shift_month(today.year, today.month, -months_back)
        rows: list[tuple[int, int, int]] = []
        while (year, month) <= (today.year, today.month):
            start, end = month_bounds(year, month)
            fixed_total = sum(
                c.amount_cents for c in fixed_repo.active_for_month(start, end))
            variable_total = expense_repo.total_for_month(year, month)
            rows.append((year, month, fixed_total + variable_total))
            year, month = dates.shift_month(year, month, 1)
        db.conn.execute("DELETE FROM interop_ausgaben_monat")
        db.conn.executemany(
            "INSERT INTO interop_ausgaben_monat (jahr, monat, summe_cent) "
            "VALUES (?, ?, ?)", rows)
        db.conn.commit()
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - never block the app over interop
        _log.warning("interop_ausgaben_monat konnte nicht aktualisiert werden: %s", exc)
        return 0


def discover_sister() -> SisterState:
    """Find the sister app (KFZ-Manager) and validate the handshake."""
    try:
        announce = family_dir(create=False) / SISTER_ANNOUNCE_FILE
        if not announce.is_file():
            return SisterState(
                status="fehlt",
                message=f"{SISTER_APP_NAME} wurde auf diesem Gerät nicht gefunden.")
        try:
            with open(announce, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            _log.info("Schwester-Ankündigung unlesbar: %s", exc)
            return SisterState(
                status="fehler",
                message=f"Die Ankündigungsdatei von {SISTER_APP_NAME} ist unlesbar.")

        version = data.get("interop_version")
        db_path = Path(str(data.get("db_path") or ""))
        app_version = str(data.get("app_version") or "")
        if not isinstance(version, int):
            return SisterState(
                status="fehler",
                message=f"{SISTER_APP_NAME} meldet keine gültige Interop-Version.")
        # Same-major handshake (interop versions are plain integers → the
        # integer IS the major).
        if version != INTEROP_VERSION:
            newer = version > INTEROP_VERSION
            which = "den HaushaltsManager" if newer else SISTER_APP_NAME
            return SisterState(
                status="version",
                message=(f"Die Apps sprechen verschiedene Interop-Versionen "
                         f"(hier v{INTEROP_VERSION}, dort v{version}). "
                         f"Bitte {which} aktualisieren."),
                app_version=app_version, interop_version=version)
        if not db_path.is_file():
            return SisterState(
                status="fehler",
                message=f"Die Datenbank von {SISTER_APP_NAME} wurde nicht gefunden.",
                app_version=app_version, interop_version=version)
        return SisterState(
            status="aktiv",
            message=f"Verbunden mit {SISTER_APP_NAME} v{app_version}.",
            db_path=db_path, app_version=app_version, interop_version=version)
    except Exception as exc:  # noqa: BLE001 - discovery must never crash the app
        _log.warning("Schwester-Erkennung fehlgeschlagen: %s", exc)
        return SisterState(status="fehler",
                           message="Die Familien-Erkennung ist fehlgeschlagen.")


def _open_readonly(db_path: Path) -> sqlite3.Connection | None:
    """Open a sister database strictly read-only.

    Returns None when the open fails — including the WAL edge case: a
    WAL-mode database may be unreadable in ``mode=ro`` when its ``-shm``
    sidecar cannot be created/locked. Per contract the integration then
    silently deactivates for this session instead of crashing.
    """
    try:
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 2000")
        # Touch the schema once: WAL/lock problems surface here, not later
        # in the middle of a query.
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        return conn
    except sqlite3.Error as exc:
        _log.info("Schwester-DB nicht lesbar (Integration deaktiviert): %s", exc)
        return None


def sister_vehicles(db_path: Path) -> list[SisterVehicle]:
    """Vehicles from the sister's ``interop_fahrzeuge`` view ([] on failure)."""
    conn = _open_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT id, name, antrieb FROM interop_fahrzeuge ORDER BY name").fetchall()
        return [SisterVehicle(id=int(r["id"]), name=str(r["name"]),
                              antrieb=str(r["antrieb"])) for r in rows]
    except (sqlite3.Error, TypeError, ValueError) as exc:
        _log.info("interop_fahrzeuge nicht verfügbar: %s", exc)
        return []
    finally:
        conn.close()


def vehicle_month_costs(db_path: Path, year: int, month: int) -> dict[int, int]:
    """Per-vehicle total for one month from ``interop_kosten_monat`` (cents)."""
    conn = _open_readonly(db_path)
    if conn is None:
        return {}
    try:
        rows = conn.execute(
            "SELECT fahrzeug_id, SUM(betrag_cent) AS total FROM interop_kosten_monat "
            "WHERE jahr = ? AND monat = ? GROUP BY fahrzeug_id",
            (year, month)).fetchall()
        return {int(r["fahrzeug_id"]): int(r["total"] or 0) for r in rows}
    except (sqlite3.Error, TypeError, ValueError) as exc:
        _log.info("interop_kosten_monat nicht verfügbar: %s", exc)
        return {}
    finally:
        conn.close()


def next_appointments(db_path: Path) -> list[SisterAppointment]:
    """Open appointments from ``interop_termine``, soonest date first."""
    conn = _open_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT fahrzeug_id, typ, faellig_datum, faellig_km, beschreibung "
            "FROM interop_termine "
            "ORDER BY COALESCE(faellig_datum, '9999-12-31')").fetchall()
        return [SisterAppointment(
            fahrzeug_id=int(r["fahrzeug_id"]), typ=str(r["typ"]),
            faellig_datum=r["faellig_datum"], faellig_km=r["faellig_km"],
            beschreibung=str(r["beschreibung"] or r["typ"])) for r in rows]
    except (sqlite3.Error, TypeError, ValueError) as exc:
        _log.info("interop_termine nicht verfügbar: %s", exc)
        return []
    finally:
        conn.close()

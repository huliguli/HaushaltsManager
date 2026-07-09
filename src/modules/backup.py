"""Database backup, restore and integrity checking (Qt-free).

The app had no safety net for haushalt.db before v2.5.0: a bad import, the
"delete all data" reset or plain file corruption meant losing the entire
financial history. This module closes that gap with SQLite's online backup
API (``Connection.backup``), which copies a consistent snapshot even while
the shared connection is in use (WAL mode) — no file-level copy races.

Backups live in ``<data_dir>/backups`` as plain SQLite files named
``haushalt-YYYYMMDD-HHMMSS-<label>.db``. A small rotation keeps the newest
``MAX_BACKUPS`` so the folder can never grow unbounded. Everything here is
platform-neutral (pathlib + sqlite3 only) so Windows and macOS behave
identically.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app_meta import data_dir
from modules.logging_setup import get_logger

_log = get_logger("backup")

MAX_BACKUPS = 10

# Labels are part of the filename, so keep them to a safe character set.
_LABEL_RE = re.compile(r"[^a-z0-9\-]")
_NAME_RE = re.compile(r"^haushalt-(\d{8})-(\d{6})(?:-(\d+))?-([a-z0-9\-]+)\.db$")

# Human-readable label texts for the restore picker.
LABEL_TEXTS = {
    "start": "Automatisch (Programmstart)",
    "manuell": "Manuell erstellt",
    "vor-import": "Vor Kontoauszug-Import",
    "vor-migration": "Vor Daten-Aktualisierung",
    "vor-loeschen": "Vor dem Löschen aller Daten",
    "vor-wiederherstellung": "Vor einer Wiederherstellung",
}


class BackupError(RuntimeError):
    """A backup or restore step failed; message is user-presentable German."""


def backups_dir(db_path: Path | None = None) -> Path:
    """Backup folder for the given database (next to the .db file).

    Backups live BESIDE the database they protect: in production that is
    ``<data_dir>/backups`` (the database sits in ``data_dir()``), and a test
    database in a temp folder gets its backups there too — a test run can
    never write into the real user profile.
    """
    base = Path(db_path).parent if db_path else data_dir()
    path = base / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created: datetime
    label: str
    size_bytes: int

    @property
    def label_text(self) -> str:
        return LABEL_TEXTS.get(self.label, self.label)


def _sanitize_label(label: str) -> str:
    cleaned = _LABEL_RE.sub("-", label.lower()).strip("-") or "manuell"
    return cleaned[:40]


def _backup_filename(directory: Path, now: datetime, label: str) -> Path:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    candidate = directory / f"haushalt-{stamp}-{label}.db"
    # Two backups within the same second (e.g. tests) get a counter suffix.
    counter = 1
    while candidate.exists():
        candidate = directory / f"haushalt-{stamp}-{counter}-{label}.db"
        counter += 1
    return candidate


def create_backup(
    conn: sqlite3.Connection,
    label: str = "manuell",
    directory: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Snapshot the live database into a new backup file and rotate.

    Raises :class:`BackupError` when the snapshot cannot be written — callers
    that are about to do something destructive (wipe, restore) must treat that
    as a hard stop (fail closed), not as a warning.
    """
    directory = directory or backups_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = _backup_filename(directory, now or datetime.now(), _sanitize_label(label))
    try:
        dest = sqlite3.connect(target)
        try:
            conn.backup(dest)
        finally:
            dest.close()
    except sqlite3.Error as exc:
        # Never leave a half-written file behind — it would look like a valid
        # backup in the restore picker.
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupError(f"Sicherung konnte nicht erstellt werden: {exc}") from exc
    _log.info("Backup erstellt: %s", target.name)
    _rotate(directory)
    return target


def _rotate(directory: Path, keep: int = MAX_BACKUPS) -> None:
    backups = list_backups(directory)
    for info in backups[keep:]:
        try:
            info.path.unlink()
            _log.info("Altes Backup entfernt: %s", info.path.name)
        except OSError:
            pass  # a locked/undeletable old backup must never block the new one


def list_backups(directory: Path | None = None) -> list[BackupInfo]:
    """All recognised backups, newest first."""
    directory = directory or backups_dir()
    result: list[BackupInfo] = []
    try:
        entries = sorted(directory.glob("haushalt-*.db"))
    except OSError:
        return []
    for path in entries:
        match = _NAME_RE.match(path.name)
        if not match:
            continue
        day, clock, counter, label = match.groups()
        try:
            created = datetime.strptime(f"{day}{clock}", "%Y%m%d%H%M%S")
            size = path.stat().st_size
        except (ValueError, OSError):
            continue
        # The counter only orders same-second backups; fold it into microseconds
        # so sorting stays purely chronological.
        if counter:
            created = created.replace(microsecond=min(999_999, int(counter)))
        result.append(BackupInfo(path=path, created=created, label=label, size_bytes=size))
    result.sort(key=lambda info: (info.created, info.path.name), reverse=True)
    return result


def startup_backup(conn: sqlite3.Connection, directory: Path | None = None) -> Path | None:
    """Create the automatic start-of-day backup (at most one per calendar day).

    Never raises: a failing automatic backup must not block the app start —
    it is logged, and manual backups from the settings remain available.
    """
    try:
        directory = directory or backups_dir()
        today = date.today()
        for info in list_backups(directory):
            if info.label == "start" and info.created.date() == today:
                return None  # already covered for today
        return create_backup(conn, label="start", directory=directory)
    except Exception as exc:  # noqa: BLE001 - deliberately never blocks startup
        _log.warning("Automatisches Start-Backup fehlgeschlagen: %s", exc)
        return None


def integrity_ok(conn: sqlite3.Connection) -> bool:
    """Fast structural check of the open database (PRAGMA quick_check)."""
    try:
        row = conn.execute("PRAGMA quick_check(1)").fetchone()
        return bool(row) and str(row[0]).lower() == "ok"
    except sqlite3.Error:
        return False


def backup_schema_version(path: Path) -> int | None:
    """Stored schema version of a backup file (None when unreadable/fresh)."""
    try:
        # as_uri() percent-encodes spaces etc., which SQLite's URI parser decodes.
        src = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            row = src.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            return int(row[0]) if row else None
        finally:
            src.close()
    except (sqlite3.Error, ValueError, TypeError, OSError):
        return None


def restore_into_connection(conn: sqlite3.Connection, backup_path: Path) -> None:
    """Replace the live database content with the given backup snapshot.

    Uses the backup API in reverse (backup file -> live connection), so the
    shared connection object every repository holds stays valid — no file
    swapping, no reopening, works identically on Windows and macOS. The
    caller must re-run schema initialisation afterwards (an older backup may
    predate the current schema) and refresh the UI.

    Raises :class:`BackupError` with a user-presentable German message when
    the backup is unreadable or damaged; the live data is only touched after
    the backup has passed its own integrity check.
    """
    if not backup_path.exists():
        raise BackupError("Die Sicherungsdatei existiert nicht mehr.")
    try:
        src = sqlite3.connect(f"{backup_path.resolve().as_uri()}?mode=ro", uri=True)
    except (sqlite3.Error, OSError) as exc:
        raise BackupError(f"Sicherung kann nicht geöffnet werden: {exc}") from exc
    try:
        row = src.execute("PRAGMA quick_check(1)").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise BackupError(
                "Die Sicherungsdatei ist beschädigt und kann nicht "
                "wiederhergestellt werden.")
        src.backup(conn)
        conn.commit()
    except sqlite3.Error as exc:
        raise BackupError(f"Wiederherstellung fehlgeschlagen: {exc}") from exc
    finally:
        src.close()
    _log.info("Datenbank aus Backup wiederhergestellt: %s", backup_path.name)


def replace_database_file(db_path: Path, backup_path: Path) -> Path:
    """File-level recovery for a database that cannot even be opened.

    Only for the corruption path at startup, where no usable connection
    exists: the damaged file is renamed aside (never deleted — it may still
    hold forensically recoverable data), its WAL/SHM sidecars are removed
    (they belong to the damaged state), and the backup is copied into place.
    Returns the path the damaged file was moved to.

    Raises :class:`BackupError` when any step fails; in that case the
    original file layout is left as intact as possible.
    """
    import shutil

    if not backup_path.exists():
        raise BackupError("Die Sicherungsdatei existiert nicht mehr.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    aside = db_path.with_name(f"{db_path.stem}-defekt-{stamp}{db_path.suffix}")
    try:
        if db_path.exists():
            db_path.rename(aside)
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        shutil.copyfile(backup_path, db_path)
    except OSError as exc:
        raise BackupError(
            f"Wiederherstellung auf Dateiebene fehlgeschlagen: {exc}") from exc
    _log.info("Beschädigte Datenbank ersetzt (%s -> %s)", aside.name, backup_path.name)
    return aside

"""Tests for database backup, restore and the open-time integrity guards."""

import sqlite3
from datetime import datetime

import pytest

from modules import backup
from modules.db_handler.database import (
    CURRENT_SCHEMA_VERSION,
    Database,
    DatabaseCorruptError,
    SchemaTooNewError,
)
from modules.db_handler.repositories import IncomeRepository
from modules.models import IncomeSource


def _db(tmp_path):
    return Database(tmp_path / "test.db")


def test_create_backup_writes_snapshot(tmp_path):
    db = _db(tmp_path)
    IncomeRepository(db).add(IncomeSource("Job", 100_000, "vollzeit"))
    target = backup.create_backup(db.conn, label="manuell", directory=tmp_path / "b")
    assert target.exists()
    src = sqlite3.connect(target)
    assert src.execute("SELECT COUNT(*) FROM income_sources").fetchone()[0] == 1
    src.close()
    db.close()


def test_rotation_keeps_only_newest(tmp_path):
    db = _db(tmp_path)
    directory = tmp_path / "b"
    for i in range(backup.MAX_BACKUPS + 3):
        backup.create_backup(db.conn, label="start", directory=directory,
                             now=datetime(2026, 1, 1, 12, 0, i))
    infos = backup.list_backups(directory)
    assert len(infos) == backup.MAX_BACKUPS
    seconds = [info.created.second for info in infos]
    assert seconds == sorted(seconds, reverse=True)  # newest first
    assert min(seconds) == 3  # the three oldest snapshots were rotated out
    db.close()


def test_startup_backup_at_most_once_per_day(tmp_path):
    db = _db(tmp_path)
    directory = tmp_path / "b"
    assert backup.startup_backup(db.conn, directory) is not None
    assert backup.startup_backup(db.conn, directory) is None
    assert len(backup.list_backups(directory)) == 1
    db.close()


def test_restore_roundtrip_and_reinitialise(tmp_path):
    db = _db(tmp_path)
    repo = IncomeRepository(db)
    repo.add(IncomeSource("Job", 100_000, "vollzeit"))
    snap = backup.create_backup(db.conn, directory=tmp_path / "b")
    repo.add(IncomeSource("Neu", 50_000, "minijob"))
    assert repo.total_active() == 150_000

    backup.restore_into_connection(db.conn, snap)
    db.reinitialise_after_restore()
    assert repo.total_active() == 100_000  # the later row is gone again
    row = db.query_one("SELECT version FROM schema_version")
    assert row["version"] == CURRENT_SCHEMA_VERSION
    db.close()


def test_restore_refuses_damaged_backup(tmp_path):
    db = _db(tmp_path)
    IncomeRepository(db).add(IncomeSource("Job", 100_000, "vollzeit"))
    bad = tmp_path / "b" / "haushalt-20260101-120000-manuell.db"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"kein sqlite")
    with pytest.raises(backup.BackupError):
        backup.restore_into_connection(db.conn, bad)
    # fail closed: the live data is untouched
    assert IncomeRepository(db).total_active() == 100_000
    db.close()


def test_backup_schema_version(tmp_path):
    db = _db(tmp_path)
    snap = backup.create_backup(db.conn, directory=tmp_path / "b")
    assert backup.backup_schema_version(snap) == CURRENT_SCHEMA_VERSION
    assert backup.backup_schema_version(tmp_path / "fehlt.db") is None
    db.close()


def test_schema_too_new_is_refused(tmp_path):
    path = tmp_path / "test.db"
    db = Database(path)
    db.conn.execute("UPDATE schema_version SET version = ?",
                    (CURRENT_SCHEMA_VERSION + 1,))
    db.conn.commit()
    db.close()
    with pytest.raises(SchemaTooNewError):
        Database(path)


def test_corrupt_file_is_detected_on_open(tmp_path):
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"x" * 4096)
    with pytest.raises(DatabaseCorruptError):
        Database(path)


def test_backup_before_migration(tmp_path):
    path = tmp_path / "test.db"
    db = Database(path)
    IncomeRepository(db).add(IncomeSource("Job", 100_000, "vollzeit"))
    db.conn.execute("UPDATE schema_version SET version = 2")
    db.conn.commit()
    db.close()

    Database(path).close()  # reopen: migrates v2 -> v3, snapshot taken first
    infos = backup.list_backups(backup.backups_dir(path))
    pre = [i for i in infos if i.label == "vor-migration"]
    assert len(pre) == 1
    # the snapshot still holds the pre-migration version marker
    assert backup.backup_schema_version(pre[0].path) == 2


def test_replace_database_file_recovers_from_corruption(tmp_path):
    path = tmp_path / "haushalt.db"
    db = Database(path)
    IncomeRepository(db).add(IncomeSource("Job", 100_000, "vollzeit"))
    snap = backup.create_backup(db.conn, directory=backup.backups_dir(path))
    db.close()

    path.write_bytes(b"kaputt")  # simulate on-disk corruption
    with pytest.raises(DatabaseCorruptError):
        Database(path)

    aside = backup.replace_database_file(path, snap)
    assert aside.exists()  # damaged file kept, only renamed
    db2 = Database(path)
    assert IncomeRepository(db2).total_active() == 100_000
    db2.close()

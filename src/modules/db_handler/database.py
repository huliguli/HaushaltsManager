"""SQLite connection management and schema initialisation.

A single connection is shared across the UI. All value binding is
parameterised; the only identifiers ever interpolated into SQL are table and
column names that originate from our own model code (never user input), so
there is no SQL-injection surface.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from app_meta import database_path, schema_path
from modules.logging_setup import get_logger

_log = get_logger("db")

CURRENT_SCHEMA_VERSION = 1


class Database:
    """Thin wrapper around a sqlite3 connection with helper CRUD methods."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else database_path()
        # check_same_thread=False: short-lived worker threads (import/update)
        # may touch the DB; we serialise access from the UI in practice.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        # Column presence per table is static (schema is fixed at v1); cache it so
        # every UPDATE does not re-run PRAGMA table_info just to touch updated_at.
        self._column_cache: dict[str, set[str]] = {}
        self._initialise()

    # -- schema -------------------------------------------------------------
    def _initialise(self) -> None:
        with open(schema_path(), "r", encoding="utf-8") as fh:
            self.conn.executescript(fh.read())
        row = self.conn.execute(
            "SELECT version FROM schema_version LIMIT 1"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (CURRENT_SCHEMA_VERSION,),
            )
            self.conn.commit()
        _log.info("Database ready at %s (schema v%s)", self.path, CURRENT_SCHEMA_VERSION)

    # -- low-level helpers --------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def insert(self, table: str, params: dict[str, Any]) -> int:
        """Parameterised INSERT. Column names come from model.to_params()."""
        cols = list(params.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_sql = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
        cur = self.conn.execute(sql, [params[c] for c in cols])
        self.conn.commit()
        return int(cur.lastrowid)

    def update(self, table: str, row_id: int, params: dict[str, Any]) -> None:
        cols = list(params.keys())
        assignments = ", ".join(f"{c} = ?" for c in cols)
        values = [params[c] for c in cols]
        # Bump updated_at where the column exists.
        touch = ", updated_at = datetime('now')" if self._has_column(table, "updated_at") else ""
        sql = f"UPDATE {table} SET {assignments}{touch} WHERE id = ?"
        self.conn.execute(sql, values + [row_id])
        self.conn.commit()

    def delete(self, table: str, row_id: int) -> None:
        self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        self.conn.commit()

    def _has_column(self, table: str, column: str) -> bool:
        cols = self._column_cache.get(table)
        if cols is None:
            rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
            cols = {r["name"] for r in rows}
            self._column_cache[table] = cols
        return column in cols

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        self.conn.executemany(sql, seq)
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

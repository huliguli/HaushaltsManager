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

CURRENT_SCHEMA_VERSION = 2

# Schema v2 (v1.6.0): the expense taxonomy was refined into finer, better-named
# categories. Legacy rows still carry the old short names, so map each old name
# to its closest new bucket — a 1:1 rename, so no existing transaction or learned
# rule is ever orphaned. "Lebensmittel" and "Sonstiges" keep their names and need
# no entry. Applied to variable_expenses.category and import_rules.category.
# The new names here MUST byte-match modules.models.EXPENSE_CATEGORIES (a guard
# test asserts this). Fixed-cost categories are a separate vocabulary and are
# intentionally left untouched.
_CATEGORY_MIGRATION_V2 = {
    "Tanken": "Auto & Tanken",
    "Freizeit": "Freizeit & Unterhaltung",
    "Kleidung": "Kleidung & Mode",
    "Drogerie": "Drogerie & Körperpflege",
    "Gesundheit": "Gesundheit & Apotheke",
    "Haushalt": "Haushalt & Möbel",
}


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
        self._migrate()
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

    def _migrate(self) -> None:
        """Apply forward-compatible schema tweaks to an existing database.

        ``executescript`` only creates *missing* tables; a column added to an
        existing table needs an explicit ``ALTER``. Each step is guarded so it is
        a no-op on a fresh database (where schema.sql already created the column)
        and never touches existing user data.
        """
        if not self._has_column("variable_expenses", "recurring"):
            self.conn.execute(
                "ALTER TABLE variable_expenses ADD COLUMN recurring INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()
            self._column_cache.pop("variable_expenses", None)
        self._migrate_expense_categories_v2()

    def _migrate_expense_categories_v2(self) -> None:
        """Rename legacy expense categories to the v2 taxonomy (run once).

        Guarded by the stored schema version so it runs exactly once on an
        existing database and is a pure no-op afterwards and on a fresh DB
        (which has no rows to rename). Each UPDATE is parameterised and only
        touches the precise old name, so it cannot corrupt unrelated data.
        """
        row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        stored = row["version"] if row else 0
        if stored >= 2:
            return
        for old, new in _CATEGORY_MIGRATION_V2.items():
            self.conn.execute(
                "UPDATE variable_expenses SET category = ? WHERE category = ?", (new, old))
            self.conn.execute(
                "UPDATE import_rules SET category = ? WHERE category = ?", (new, old))
        # Bump the existing version row; a fresh DB has none yet and gets the
        # current version inserted by _initialise right after this returns.
        if row is not None:
            self.conn.execute("UPDATE schema_version SET version = 2")
        self.conn.commit()

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

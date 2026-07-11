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

CURRENT_SCHEMA_VERSION = 5


class DatabaseCorruptError(RuntimeError):
    """The database file failed its integrity check on open."""


class SchemaTooNewError(RuntimeError):
    """The database was written by a NEWER app version.

    Running old code against a newer schema is undefined behaviour (missing
    columns, half-understood data), so the open is refused instead — the data
    stays untouched and the message tells the user what to do.
    """

# Every table that holds user-entered or imported financial data. The single
# source of truth for the "delete all data" reset — a new table must be added
# here so the reset can never leave orphaned rows behind (schema_version and the
# UI-only key/value settings table are intentionally excluded; the reset clears
# data, not the schema or the theme/window preferences).
WIPE_TABLES = (
    "variable_expenses",
    "variable_income",
    "fixed_costs",
    "income_sources",
    "credits",
    "monthly_summary",
    "category_budgets",
    "import_rules",
    "import_log",
    "bank_profiles",
    "savings_goals",
    "subscription_ignores",
)

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
        try:
            try:
                self.conn.execute("PRAGMA foreign_keys = ON")
                # journal_mode reads the file header, so a non-database file
                # already fails here — surface it as the same corruption error.
                self.conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.DatabaseError as exc:
                raise DatabaseCorruptError(
                    "Die Datenbank ist beschädigt und kann nicht geöffnet "
                    f"werden.\nDatei: {self.path}") from exc
            self._guard_before_schema_work()
            # Column presence per table is static (schema is fixed at v1); cache
            # it so UPDATEs do not re-run PRAGMA table_info to touch updated_at.
            self._column_cache: dict[str, set[str]] = {}
            self._initialise()
        except BaseException:
            # A failed open must not keep the file locked — the recovery path
            # (rename aside + restore a backup) needs the handle released,
            # especially on Windows where open files cannot be renamed.
            self.conn.close()
            raise

    # -- schema -------------------------------------------------------------
    def _guard_before_schema_work(self) -> None:
        """Integrity check, downgrade guard and pre-migration backup.

        Runs BEFORE ``executescript``/``_migrate`` ever touch the file: a
        corrupt database or one written by a newer app version must be
        refused while its bytes are still exactly as found on disk.
        """
        from modules import backup

        if not backup.integrity_ok(self.conn):
            raise DatabaseCorruptError(
                "Die Datenbank ist beschädigt und kann nicht geöffnet werden.\n"
                f"Datei: {self.path}")
        stored = self._stored_schema_version()
        if stored is not None and stored > CURRENT_SCHEMA_VERSION:
            raise SchemaTooNewError(
                "Die Daten wurden mit einer neueren Programmversion "
                f"gespeichert (Datenstand v{stored}, dieses Programm kennt "
                f"v{CURRENT_SCHEMA_VERSION}).\nBitte installiere die aktuelle "
                "Version des HaushaltsManagers — deine Daten bleiben unverändert.")
        if stored is not None and stored < CURRENT_SCHEMA_VERSION:
            # Snapshot before the (additive) migration runs. A failing backup
            # is logged but does not block the start: migrations are additive
            # by contract, and refusing to start over an unwritable backups
            # folder would lock the user out of their own data.
            try:
                backup.create_backup(
                    self.conn, label="vor-migration",
                    directory=backup.backups_dir(self.path))
            except Exception as exc:  # noqa: BLE001
                _log.warning("Backup vor Migration fehlgeschlagen: %s", exc)

    def _stored_schema_version(self) -> int | None:
        """Schema version recorded in the file (None on a fresh database)."""
        try:
            row = self.conn.execute(
                "SELECT version FROM schema_version LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            return None  # table missing = fresh database
        return int(row["version"]) if row else None

    def reinitialise_after_restore(self) -> None:
        """Re-run schema setup after a backup was restored into the connection.

        A restored snapshot may predate the current schema, so the same
        idempotent path as a normal open runs again (CREATE IF NOT EXISTS +
        guarded migrations). The cached column info is stale after the
        content swap and must be rebuilt.
        """
        self._column_cache.clear()
        self._initialise()

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
        # Partial index for the recurring-template scan. Created here, after the
        # recurring column is guaranteed to exist (the ALTER above runs after
        # schema.sql), so a pre-1.4 upgrade never indexes a missing column.
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_var_recurring "
            "ON variable_expenses(recurring) WHERE recurring = 1")
        self.conn.commit()
        # v4 columns: recurring cadence + end date, and the import-batch
        # bookkeeping that makes "undo last import" possible. Guarded ALTERs,
        # no-ops on a fresh DB (schema.sql already has them).
        v4_columns = (
            ("variable_expenses", "recur_interval_months",
             "INTEGER NOT NULL DEFAULT 1"),
            ("variable_expenses", "recur_end", "TEXT"),
            ("import_log", "batch_id", "TEXT"),
            ("import_log", "created_kind", "TEXT"),
            ("import_log", "created_row_id", "INTEGER"),
        )
        for table, column, decl in v4_columns:
            if not self._has_column(table, column):
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
                self._column_cache.pop(table, None)
        self.conn.commit()
        self._migrate_expense_categories_v2()
        self._migrate_v3()
        self._migrate_v4()
        self._migrate_v5()

    def _migrate_v3(self) -> None:
        """Record schema v3 on an existing database (run once).

        The v3 additions (``category_budgets`` table and the ``idx_var_recurring``
        partial index) are created by ``schema.sql`` via ``CREATE ... IF NOT
        EXISTS`` on every start, so there is no column/data change to apply here —
        only the stored version needs bumping so downgrade guards and future
        migrations see the correct level. A no-op on a fresh DB (row is None →
        _initialise inserts the current version) and once already at v3.
        """
        row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None or row["version"] >= 3:
            return
        self.conn.execute("UPDATE schema_version SET version = 3")
        self.conn.commit()

    def _migrate_v4(self) -> None:
        """Record schema v4 on an existing database (run once).

        The v4 additions are pure column additions handled by the guarded
        ALTERs in :meth:`_migrate`; only the stored version needs bumping so
        the forward guard and future migrations see the correct level.
        """
        row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None or row["version"] >= 4:
            return
        self.conn.execute("UPDATE schema_version SET version = 4")
        self.conn.commit()

    def _migrate_v5(self) -> None:
        """Record schema v5 on an existing database (run once).

        The v5 additions (``savings_goals`` and ``subscription_ignores``) are
        whole new tables created by ``schema.sql`` via ``CREATE ... IF NOT
        EXISTS`` on every start — no column or data change to apply here, only
        the stored version needs bumping for the forward guard.
        """
        row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None or row["version"] >= 5:
            return
        self.conn.execute("UPDATE schema_version SET version = 5")
        self.conn.commit()

    def wipe_financial_data(self) -> None:
        """Delete all rows from every financial table in one transaction.

        Single source of truth for the "delete all data" reset (see WIPE_TABLES):
        clearing them together avoids the class of bug where a newly added table
        (e.g. variable_income) is forgotten and leaves orphaned rows that keep
        surfacing (inflated income, blocked re-imports) after a full reset.
        """
        for table in WIPE_TABLES:
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()

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

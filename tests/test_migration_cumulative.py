"""Cumulative upgrade test: a raw pre-1.4 database -> current schema in one open.

This is the exact path a real user takes when upgrading to v2.0.0: an old
database that lacks the ``recurring`` column, has no ``variable_income`` /
``category_budgets`` tables, carries the legacy expense-category names and sits
at ``schema_version = 1`` must be lifted all the way to the current level in a
single ``Database()`` open — WITHOUT losing or altering a single stored amount.
"""

import sqlite3

from modules.db_handler.database import CURRENT_SCHEMA_VERSION, Database
from modules.db_handler.repositories import (
    CreditRepository,
    FixedCostRepository,
    IncomeRepository,
    VariableExpenseRepository,
)


def _build_pre_1_4_db(path):
    """Hand-build a realistic pre-1.4 database (no recurring, no variable_income)."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    con.execute("INSERT INTO schema_version (version) VALUES (1)")
    # variable_expenses WITHOUT the recurring column, with legacy category names.
    con.execute(
        "CREATE TABLE variable_expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "date TEXT NOT NULL, amount_cents INTEGER NOT NULL DEFAULT 0, "
        "category TEXT NOT NULL DEFAULT 'Sonstiges', description TEXT, "
        "receipt_path TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    con.executemany(
        "INSERT INTO variable_expenses (date, amount_cents, category) VALUES (?, ?, ?)",
        [("2025-11-03", 4_299, "Tanken"),          # legacy name -> "Auto & Tanken"
         ("2025-11-07", 6_150, "Lebensmittel"),    # unchanged
         ("2025-12-01", 1_999, "Drogerie")])       # legacy name -> "Drogerie & Körperpflege"
    con.execute(
        "CREATE TABLE income_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL, amount_cents INTEGER NOT NULL DEFAULT 0, "
        "income_type TEXT NOT NULL DEFAULT 'sonstiges', active INTEGER NOT NULL DEFAULT 1, "
        "note TEXT, created_at TEXT, updated_at TEXT)")
    con.execute("INSERT INTO income_sources (name, amount_cents, income_type) "
                "VALUES ('Teilzeit', 210_000, 'teilzeit')")
    con.execute(
        "CREATE TABLE fixed_costs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
        "amount_cents INTEGER NOT NULL DEFAULT 0, category TEXT NOT NULL DEFAULT 'Sonstiges', "
        "start_date TEXT, end_date TEXT, note TEXT, active INTEGER NOT NULL DEFAULT 1, "
        "created_at TEXT, updated_at TEXT)")
    con.execute("INSERT INTO fixed_costs (name, amount_cents, category) "
                "VALUES ('Miete', 78_000, 'Wohnen')")
    con.execute(
        "CREATE TABLE credits (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
        "total_cents INTEGER, monthly_cents INTEGER, start_date TEXT, end_date TEXT, "
        "term_months INTEGER, interest_rate REAL, category TEXT NOT NULL DEFAULT 'Divers', "
        "note TEXT, status TEXT NOT NULL DEFAULT 'aktiv', linked_fixed_cost_id INTEGER, "
        "created_at TEXT, updated_at TEXT)")
    con.execute("INSERT INTO credits (name, total_cents, monthly_cents, category) "
                "VALUES ('Autokredit', 1_500_000, 25_000, 'Auto')")
    # Legacy learned import rule with an old category name.
    con.execute(
        "CREATE TABLE import_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, pattern TEXT NOT NULL, "
        "category TEXT NOT NULL, learned INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL "
        "DEFAULT 100, created_at TEXT, UNIQUE(pattern))")
    con.execute("INSERT INTO import_rules (pattern, category) VALUES ('aral tankstelle', 'Tanken')")
    con.commit()
    con.close()


def test_cumulative_pre_1_4_upgrade_preserves_all_data(tmp_path):
    path = tmp_path / "legacy.db"
    _build_pre_1_4_db(path)

    db = Database(path)  # single open must run every pending migration

    # 1) schema level advanced to the current version.
    version = db.query_one("SELECT version FROM schema_version LIMIT 1")["version"]
    assert version == CURRENT_SCHEMA_VERSION

    # 2) the recurring column now exists and old rows default to non-recurring.
    exp = VariableExpenseRepository(db)
    nov = exp.list_for_month(2025, 11)
    assert {e.amount_cents for e in nov} == {4_299, 6_150}
    assert all(e.recurring is False for e in nov)

    # 3) legacy categories were renamed to the v2 taxonomy (data preserved).
    cats = [r["category"] for r in db.query(
        "SELECT category FROM variable_expenses ORDER BY id")]
    assert cats == ["Auto & Tanken", "Lebensmittel", "Drogerie & Körperpflege"]
    rule_cat = db.query_one(
        "SELECT category FROM import_rules WHERE pattern = 'aral tankstelle'")["category"]
    assert rule_cat == "Auto & Tanken"

    # 4) the new tables were created and start empty — no crash reading them.
    assert db.query_one("SELECT COUNT(*) AS n FROM variable_income")["n"] == 0
    assert db.query_one("SELECT COUNT(*) AS n FROM category_budgets")["n"] == 0
    assert db.query_one("SELECT COUNT(*) AS n FROM monthly_summary")["n"] == 0
    # v5 additions (savings goals + Abo-Radar ignores) arrive the same way.
    assert db.query_one("SELECT COUNT(*) AS n FROM savings_goals")["n"] == 0
    assert db.query_one("SELECT COUNT(*) AS n FROM subscription_ignores")["n"] == 0

    # 5) every pre-existing amount survived untouched.
    assert IncomeRepository(db).total_active() == 210_000
    assert FixedCostRepository(db).total_active() == 78_000
    credit = CreditRepository(db).list()[0]
    assert credit.total_cents == 1_500_000 and credit.monthly_cents == 25_000

    # 6) the recurring partial index exists (created in _migrate, not schema.sql).
    idx = db.query("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_var_recurring'")
    assert len(idx) == 1
    db.close()

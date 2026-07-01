"""Tests for the database layer and repositories (temp DB, no app data dir)."""

from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    CreditRepository,
    FixedCostRepository,
    IncomeRepository,
    SettingsRepository,
    VariableExpenseRepository,
)
from modules.models import Credit, FixedCost, IncomeSource, VariableExpense


def _db(tmp_path):
    return Database(tmp_path / "test.db")


def test_income_crud_and_total(tmp_path):
    db = _db(tmp_path)
    repo = IncomeRepository(db)
    repo.add(IncomeSource("Nebenjob", 50_000, "minijob"))
    tid = repo.add(IncomeSource("Anstellung", 180_000, "teilzeit"))
    repo.add(IncomeSource("Inaktiv", 99_900, "sonstiges", active=False))
    assert repo.total_active() == 230_000  # inactive excluded

    item = repo.get(tid)
    item.amount_cents = 210_000
    repo.update(item)
    assert repo.get(tid).amount_cents == 210_000

    repo.delete(tid)
    assert repo.get(tid) is None
    db.close()


def test_fixed_active_for_month(tmp_path):
    db = _db(tmp_path)
    repo = FixedCostRepository(db)
    repo.add(FixedCost("Miete", 50_000, "Wohnen"))  # open-ended
    repo.add(FixedCost("Kredit", 7_500, "Kredit", end_date="2026-12-14"))
    repo.add(FixedCost("Zukunft", 1_000, "Sonstiges", start_date="2030-01-01"))

    active = repo.active_for_month("2026-06-01", "2026-06-30")
    names = {c.name for c in active}
    assert "Miete" in names and "Kredit" in names
    assert "Zukunft" not in names  # starts in 2030
    assert repo.total_active() == 58_500
    db.close()


def test_variable_aggregates(tmp_path):
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense("2026-06-05", 3_000, "Lebensmittel"))
    repo.add(VariableExpense("2026-06-10", 5_000, "Auto & Tanken"))
    repo.add(VariableExpense("2026-06-15", 2_000, "Lebensmittel"))
    repo.add(VariableExpense("2026-07-01", 9_900, "Freizeit & Unterhaltung"))  # other month

    assert repo.total_for_range("2026-06-01", "2026-06-30") == 10_000
    by_cat = repo.by_category_for_range("2026-06-01", "2026-06-30")
    assert by_cat["Lebensmittel"] == 5_000
    assert by_cat["Auto & Tanken"] == 5_000
    db.close()


def test_recurring_expense_appears_every_month(tmp_path):
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense("2026-06-05", 3_000, "Lebensmittel", "Edeka"))
    repo.add(VariableExpense("2026-06-15", 5_000, "Freizeit & Unterhaltung", "Abo", recurring=True))

    # June: one-off + recurring.
    assert repo.total_for_month(2026, 6) == 8_000
    assert {e.amount_cents for e in repo.list_for_month(2026, 6)} == {3_000, 5_000}
    # July: only the recurring, materialised into July.
    july = repo.list_for_month(2026, 7)
    assert len(july) == 1
    assert july[0].amount_cents == 5_000 and july[0].recurring is True
    assert july[0].date.startswith("2026-07") and july[0].id is not None
    assert repo.total_for_month(2026, 7) == 5_000
    # May (before the start): nothing.
    assert repo.list_for_month(2026, 5) == []
    assert repo.total_for_month(2026, 5) == 0
    db.close()


def test_recurring_by_category_and_day_clamp(tmp_path):
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense("2026-01-31", 2_000, "Haushalt & Möbel", "Putzmittel", recurring=True))
    feb = repo.list_for_month(2026, 2)               # 2026 February has 28 days
    assert feb[0].date == "2026-02-28"               # day clamped to month length
    assert repo.by_category_for_month(2026, 2)["Haushalt & Möbel"] == 2_000
    db.close()


def test_recurring_excluded_from_raw_range(tmp_path):
    # Range aggregates count only one-off expenses; the month methods add the
    # recurring ones, so the dashboard never double-counts.
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense("2026-06-05", 3_000, "Lebensmittel"))
    repo.add(VariableExpense("2026-06-15", 5_000, "Freizeit & Unterhaltung", recurring=True))
    assert repo.total_for_range("2026-06-01", "2026-06-30") == 3_000
    db.close()


def test_migration_adds_recurring_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    # Simulate a pre-1.4.0 database: variable_expenses without the recurring column.
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE variable_expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "date TEXT NOT NULL, amount_cents INTEGER NOT NULL DEFAULT 0, "
        "category TEXT NOT NULL DEFAULT 'Sonstiges', description TEXT, "
        "receipt_path TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    con.execute("INSERT INTO variable_expenses (date, amount_cents, category) "
                "VALUES ('2026-06-01', 1000, 'Lebensmittel')")
    con.commit()
    con.close()
    # Opening through Database must add the column and keep the existing row.
    db = Database(path)
    items = VariableExpenseRepository(db).list_for_month(2026, 6)
    assert len(items) == 1
    assert items[0].recurring is False and items[0].amount_cents == 1000
    db.close()


def test_variable_income_is_month_scoped(tmp_path):
    # One-off (imported) income counts only in its booking month and is never
    # carried into other months — a single credit must not become recurring.
    from modules.db_handler.repositories import VariableIncomeRepository
    from modules.models import VariableIncome
    db = _db(tmp_path)
    repo = VariableIncomeRepository(db)
    repo.add(VariableIncome("2026-05-15", 5_000, "Freund Essen"))
    rid = repo.add(VariableIncome("2026-05-20", 200_000, "Gehalt Mai"))
    repo.add(VariableIncome("2026-06-01", 3_000, "Juni"))
    assert repo.total_for_month(2026, 5) == 205_000
    assert repo.total_for_month(2026, 7) == 0          # nothing carried over
    assert len(repo.list_for_month(2026, 5)) == 2
    repo.delete(rid)
    assert repo.total_for_month(2026, 5) == 5_000
    db.close()


def test_credit_and_settings(tmp_path):
    db = _db(tmp_path)
    credits = CreditRepository(db)
    cid = credits.add(Credit("Autokredit", total_cents=1_500_000,
                             monthly_cents=25_000, category="Auto"))
    assert credits.get(cid).name == "Autokredit"
    assert len(credits.list()) == 1

    settings = SettingsRepository(db)
    settings.set("theme", "dark")
    assert settings.get("theme") == "dark"
    settings.set("theme", "light")          # upsert
    assert settings.get("theme") == "light"
    assert settings.get("missing", "fallback") == "fallback"
    db.close()


def test_migration_renames_expense_categories_v2(tmp_path):
    # A pre-v2 database (schema_version = 1) carries the old short category
    # names; opening it must rename them to the v2 taxonomy in BOTH
    # variable_expenses and import_rules, leave unrelated rows alone, lose no
    # data, and bump the schema version to 2.
    path = tmp_path / "v1.db"
    db = Database(path)
    # Roll the version back and plant legacy-named rows to simulate v1.
    db.conn.execute("UPDATE schema_version SET version = 1")
    db.conn.execute("INSERT INTO variable_expenses (date, amount_cents, category) "
                    "VALUES ('2026-05-10', 1234, 'Tanken')")
    db.conn.execute("INSERT INTO variable_expenses (date, amount_cents, category) "
                    "VALUES ('2026-05-11', 999, 'Lebensmittel')")
    db.conn.execute("INSERT INTO import_rules (pattern, category, learned) "
                    "VALUES ('alte tanke', 'Tanken', 1)")
    db.conn.commit()
    db.close()

    db2 = Database(path)  # reopen -> migration fires
    cats = [r["category"] for r in db2.query(
        "SELECT category FROM variable_expenses ORDER BY id")]
    rule_cat = db2.query_one(
        "SELECT category FROM import_rules WHERE pattern = 'alte tanke'")["category"]
    version = db2.query_one("SELECT version FROM schema_version LIMIT 1")["version"]
    assert cats == ["Auto & Tanken", "Lebensmittel"]   # renamed + unrelated kept
    assert rule_cat == "Auto & Tanken"                 # learned rule renamed too
    assert len(cats) == 2                              # no data lost
    assert version == 2
    db2.close()


def test_migration_targets_and_seed_rules_in_taxonomy():
    # Single source of truth: every v2 migration target and every category the
    # categoriser can emit must exist in EXPENSE_CATEGORIES.
    from modules.bank_import.seed_rules import SEED_RULES
    from modules.db_handler.database import _CATEGORY_MIGRATION_V2
    from modules.models import EXPENSE_CATEGORIES

    valid = set(EXPENSE_CATEGORIES)
    assert all(new in valid for new in _CATEGORY_MIGRATION_V2.values())
    assert all(cat in valid for _pattern, cat in SEED_RULES)


def test_imported_posting_single_month_no_carryover(tmp_path):
    # A6: an imported bank posting is one-off (recurring=False); it shows in its
    # booking month only and is NEVER carried into a later month, while a real
    # recurring template would be. Guards against import postings being
    # materialised every month (double counting).
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense("2026-06-15", 3_490, "Lebensmittel", "REWE", recurring=False))
    assert len(repo.list_for_month(2026, 6)) == 1     # present in its month
    assert repo.list_for_month(2026, 7) == []         # NOT carried into July
    assert repo.total_for_month(2026, 7) == 0
    db.close()

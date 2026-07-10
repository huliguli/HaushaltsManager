"""Tests for v2.7.0: recurring cadences (quarterly/yearly, end date) and the
reversible import batches ("Letzten Import rückgängig")."""

from modules.bank_import.commit import commit_transactions, rollback_batch
from modules.bank_import.model import BankTransaction, transaction_hash
from modules.db_handler.database import CURRENT_SCHEMA_VERSION, Database
from modules.db_handler.repositories import (
    ImportLogRepository,
    ImportRuleRepository,
    VariableExpenseRepository,
    VariableIncomeRepository,
)
from modules.models import VariableExpense


def _db(tmp_path):
    return Database(tmp_path / "test.db")


# --- recurring cadences ------------------------------------------------------

def test_quarterly_occurs_every_third_month(tmp_path):
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense(date="2026-01-15", amount_cents=9_000,
                             category="Versicherung", description="Kfz",
                             recurring=True, interval_months=3))
    assert repo.total_for_month(2026, 1) == 9_000   # start month
    assert repo.total_for_month(2026, 2) == 0       # between occurrences
    assert repo.total_for_month(2026, 3) == 0
    assert repo.total_for_month(2026, 4) == 9_000   # +3 months
    assert repo.total_for_month(2026, 7) == 9_000   # +6 months
    assert repo.total_for_month(2025, 12) == 0      # before the start
    db.close()


def test_yearly_occurs_once_a_year_with_day_clamp(tmp_path):
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense(date="2024-02-29", amount_cents=21_000,
                             category="Finanzen & Gebühren", description="GEZ-Jahr",
                             recurring=True, interval_months=12))
    assert repo.total_for_month(2024, 2) == 21_000
    assert repo.total_for_month(2024, 8) == 0
    assert repo.total_for_month(2025, 2) == 21_000
    # Non-leap February: the day is clamped to the 28th, not dropped.
    occ = [e for e in repo.list_for_month(2025, 2) if e.recurring]
    assert occ and occ[0].date == "2025-02-28"
    db.close()


def test_recur_end_stops_the_recurrence(tmp_path):
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense(date="2026-01-10", amount_cents=1_500,
                             category="Streaming & Abos", description="Abo",
                             recurring=True, interval_months=1,
                             recur_end="2026-03-31"))
    assert repo.total_for_month(2026, 3) == 1_500   # last covered month
    assert repo.total_for_month(2026, 4) == 0       # ended
    db.close()


def test_monthly_default_unchanged(tmp_path):
    """The pre-v2.7 behaviour (recurring = every month) must stay identical."""
    db = _db(tmp_path)
    repo = VariableExpenseRepository(db)
    repo.add(VariableExpense(date="2026-05-31", amount_cents=2_000,
                             category="Sonstiges", recurring=True))
    assert repo.total_for_month(2026, 5) == 2_000
    assert repo.total_for_month(2026, 6) == 2_000   # day clamped to 30
    occ = [e for e in repo.list_for_month(2026, 6) if e.recurring]
    assert occ and occ[0].date == "2026-06-30"
    db.close()


def test_migration_bumps_to_v4_and_adds_columns(tmp_path):
    path = tmp_path / "test.db"
    db = Database(path)
    db.conn.execute("UPDATE schema_version SET version = 3")
    db.conn.commit()
    db.close()
    db = Database(path)  # reopen: v3 -> v4
    version = db.query_one("SELECT version FROM schema_version LIMIT 1")["version"]
    assert version == CURRENT_SCHEMA_VERSION == 4
    cols = {r["name"] for r in db.query("PRAGMA table_info(variable_expenses)")}
    assert {"recur_interval_months", "recur_end"} <= cols
    cols = {r["name"] for r in db.query("PRAGMA table_info(import_log)")}
    assert {"batch_id", "created_kind", "created_row_id"} <= cols
    db.close()


# --- reversible import batches ------------------------------------------------

def _txs():
    return [
        BankTransaction(booking_date="2026-06-03", amount_cents=-4_299,
                        payee="ARAL", category="Auto & Tanken"),
        BankTransaction(booking_date="2026-06-05", amount_cents=-1_299,
                        payee="NETFLIX", category="Streaming & Abos"),
        BankTransaction(booking_date="2026-06-10", amount_cents=50_000,
                        payee="Max Mustermann", purpose="Rueckzahlung"),
    ]


def test_rollback_batch_removes_rows_and_hashes(tmp_path):
    db = _db(tmp_path)
    exp = VariableExpenseRepository(db)
    inc = VariableIncomeRepository(db)
    rules = ImportRuleRepository(db)
    log = ImportLogRepository(db)

    txs = _txs()
    n_exp, n_inc = commit_transactions(txs, exp, inc, rules, log, batch_id="b1")
    assert (n_exp, n_inc) == (2, 1)
    assert exp.total_for_month(2026, 6) == 5_598
    assert inc.total_for_month(2026, 6) == 50_000

    info = log.latest_batch()
    assert info is not None and info[0] == "b1" and info[1] == 3

    removed_exp, removed_inc = rollback_batch("b1", exp, inc, log)
    assert (removed_exp, removed_inc) == (2, 1)
    assert exp.total_for_month(2026, 6) == 0
    assert inc.total_for_month(2026, 6) == 0
    # Hashes are gone too, so the same statement imports again afterwards.
    assert log.known([transaction_hash(t) for t in txs]) == set()
    assert log.latest_batch() is None
    # Learned rules survive on purpose (they encode the user's mapping).
    assert ("aral", "Auto & Tanken") in rules.rules()
    db.close()


def test_latest_batch_ignores_legacy_rows(tmp_path):
    db = _db(tmp_path)
    log = ImportLogRepository(db)
    log.add("legacy-hash", "2026-01-01", -1_000)  # pre-v2.7 row: no batch_id
    assert log.latest_batch() is None
    log.add("new-hash", "2026-06-01", -2_000,
            batch_id="b2", created_kind="expense", created_row_id=1)
    info = log.latest_batch()
    assert info is not None and info[0] == "b2" and info[1] == 1
    db.close()

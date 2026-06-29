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
    repo.add(VariableExpense("2026-06-10", 5_000, "Tanken"))
    repo.add(VariableExpense("2026-06-15", 2_000, "Lebensmittel"))
    repo.add(VariableExpense("2026-07-01", 9_900, "Freizeit"))  # other month

    assert repo.total_for_range("2026-06-01", "2026-06-30") == 10_000
    by_cat = repo.by_category_for_range("2026-06-01", "2026-06-30")
    assert by_cat["Lebensmittel"] == 5_000
    assert by_cat["Tanken"] == 5_000
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

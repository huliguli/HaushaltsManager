"""Tests for savings goals: derived progress (modules.savings_goals) and the
repository (schema v5)."""

from datetime import date

from modules import savings_goals
from modules.db_handler.database import Database
from modules.db_handler.repositories import SavingsGoalRepository
from modules.models import SavingsGoal

TODAY = date(2026, 7, 15)


def test_progress_counts_start_month_and_rate():
    g = SavingsGoal("Urlaub", target_cents=120_000, monthly_cents=10_000,
                    start_date="2026-03-01")
    p = savings_goals.compute(g, today=TODAY)
    assert p.months_elapsed == 5                 # Mär, Apr, Mai, Jun, Jul
    assert p.saved_cents == 50_000
    assert p.remaining_cents == 70_000
    assert not p.reached
    assert abs(p.ratio - 50_000 / 120_000) < 1e-9


def test_manual_correction_is_added_and_floor_is_zero():
    g = SavingsGoal("Puffer", target_cents=100_000, monthly_cents=10_000,
                    start_date="2026-06-01", manual_cents=25_000)
    p = savings_goals.compute(g, today=TODAY)
    assert p.saved_cents == 2 * 10_000 + 25_000  # Jun + Jul + Startguthaben
    # A large negative correction can never push the state below zero.
    g_neg = SavingsGoal("Minus", target_cents=100_000, monthly_cents=10_000,
                        start_date="2026-06-01", manual_cents=-99_000)
    assert savings_goals.compute(g_neg, today=TODAY).saved_cents == 0


def test_future_start_counts_nothing_yet():
    g = SavingsGoal("Später", target_cents=50_000, monthly_cents=5_000,
                    start_date="2026-10-01")
    p = savings_goals.compute(g, today=TODAY)
    assert p.months_elapsed == 0 and p.saved_cents == 0


def test_eta_and_months_to_go():
    # 70.000 fehlen bei 10.000/Monat -> 7 weitere Raten, ab nächstem Monat.
    g = SavingsGoal("Urlaub", target_cents=120_000, monthly_cents=10_000,
                    start_date="2026-03-01")
    p = savings_goals.compute(g, today=TODAY)
    assert p.months_to_go == 7
    assert p.eta == (2027, 2)
    assert "2027" in savings_goals.eta_label(p)


def test_reached_goal_is_capped_and_labelled():
    g = SavingsGoal("Fertig", target_cents=30_000, monthly_cents=10_000,
                    start_date="2026-01-01")
    p = savings_goals.compute(g, today=TODAY)
    assert p.reached and p.ratio == 1.0 and p.remaining_cents == 0
    assert p.months_to_go == 0 and p.eta is None
    assert savings_goals.eta_label(p) == "Ziel erreicht"


def test_zero_rate_has_no_eta():
    g = SavingsGoal("Ruht", target_cents=50_000, monthly_cents=0,
                    start_date="2026-01-01", manual_cents=10_000)
    p = savings_goals.compute(g, today=TODAY)
    assert p.saved_cents == 10_000
    assert p.months_to_go is None and p.eta is None
    assert savings_goals.eta_label(p) == "ohne Sparrate offen"


def test_repository_crud_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    repo = SavingsGoalRepository(db)
    gid = repo.add(SavingsGoal("Urlaub", target_cents=120_000,
                               monthly_cents=10_000, start_date="2026-03-01",
                               note="Sommer"))
    stored = repo.get(gid)
    assert stored.name == "Urlaub" and stored.target_cents == 120_000
    assert stored.start_date == "2026-03-01" and stored.note == "Sommer"

    stored.manual_cents = 5_000
    repo.update(stored)
    assert repo.get(gid).manual_cents == 5_000

    assert len(repo.list()) == 1
    repo.delete(gid)
    assert repo.list() == []
    db.close()


def test_goal_without_start_date_defaults_to_today(tmp_path):
    db = Database(tmp_path / "test.db")
    repo = SavingsGoalRepository(db)
    gid = repo.add(SavingsGoal("Ohne Start", target_cents=10_000, monthly_cents=1_000))
    stored = repo.get(gid)
    assert stored.start_date is not None      # NOT-NULL-Spalte wurde befüllt
    p = savings_goals.compute(stored)
    assert p.months_elapsed == 1              # aktueller Monat zählt bereits
    db.close()


def test_wipe_clears_goals_and_ignores(tmp_path):
    from modules.db_handler.repositories import SubscriptionIgnoreRepository
    db = Database(tmp_path / "test.db")
    SavingsGoalRepository(db).add(SavingsGoal("X", 1_000, 100))
    ignores = SubscriptionIgnoreRepository(db)
    ignores.add("netflix")
    db.wipe_financial_data()
    assert SavingsGoalRepository(db).list() == []
    assert ignores.all() == set()
    db.close()

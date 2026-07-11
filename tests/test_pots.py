"""Tests for Töpfe: derived balances, allocation check, transfers, cascades
(modules.pots + the schema-v6 repositories)."""

from datetime import date

from modules import pots, savings_goals
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    PotMovementRepository,
    PotRepository,
    SavingsAccountRepository,
    SavingsGoalRepository,
)
from modules.models import Pot, PotMovement, SavingsAccount, SavingsGoal

TODAY = date(2026, 7, 15)


def _repos(tmp_path):
    db = Database(tmp_path / "test.db")
    return (db, SavingsAccountRepository(db), PotRepository(db),
            PotMovementRepository(db))


def test_rate_part_counts_start_month_inclusive():
    pot = Pot(account_id=1, name="Urlaub", monthly_cents=10_000,
              rate_start="2026-03-01")
    assert pots.rate_part(pot, TODAY) == 5 * 10_000     # Mär..Jul
    # Future start or no rate contributes nothing.
    assert pots.rate_part(Pot(1, "X", monthly_cents=10_000,
                              rate_start="2026-10-01"), TODAY) == 0
    assert pots.rate_part(Pot(1, "X", monthly_cents=0,
                              rate_start="2026-01-01"), TODAY) == 0


def test_balance_is_rate_plus_movements(tmp_path):
    db, accounts, pot_repo, moves = _repos(tmp_path)
    acc_id = accounts.add(SavingsAccount("Sparkonto", balance_cents=100_000))
    pot_id = pot_repo.add(Pot(acc_id, "Urlaub", monthly_cents=10_000,
                              rate_start="2026-05-01"))
    moves.add(PotMovement(pot_id, "2026-05-02", 20_000, "Startbestand"))
    moves.add(PotMovement(pot_id, "2026-06-10", -5_000, "Entnahme"))

    overview = pots.build_overview(accounts, pot_repo, moves, today=TODAY)
    state = overview[0].pots[0]
    assert state.rate_cents == 3 * 10_000               # Mai, Jun, Jul
    assert state.moved_cents == 15_000
    assert state.balance_cents == 45_000
    assert overview[0].allocated_cents == 45_000
    assert overview[0].unallocated_cents == 55_000      # 1.000 € − 450 €
    db.close()


def test_over_allocation_is_negative_not_hidden(tmp_path):
    db, accounts, pot_repo, moves = _repos(tmp_path)
    acc_id = accounts.add(SavingsAccount("Klein", balance_cents=10_000))
    pot_id = pot_repo.add(Pot(acc_id, "Zuviel"))
    moves.add(PotMovement(pot_id, "2026-07-01", 25_000))
    overview = pots.build_overview(accounts, pot_repo, moves, today=TODAY)
    assert overview[0].unallocated_cents == -15_000
    db.close()


def test_transfer_is_atomic_double_booking(tmp_path):
    db, accounts, pot_repo, moves = _repos(tmp_path)
    acc_id = accounts.add(SavingsAccount("Konto", balance_cents=50_000))
    a = pot_repo.add(Pot(acc_id, "A"))
    b = pot_repo.add(Pot(acc_id, "B"))
    moves.add(PotMovement(a, "2026-07-01", 30_000))

    moves.transfer(a, b, 12_000, "2026-07-10", "Umbuchung")
    sums = moves.sums_by_pot()
    assert sums[a] == 18_000 and sums[b] == 12_000
    # Total money is unchanged by a transfer.
    assert sums[a] + sums[b] == 30_000
    # Same-pot and zero transfers are ignored.
    moves.transfer(a, a, 5_000, "2026-07-10")
    moves.transfer(a, b, 0, "2026-07-10")
    assert moves.sums_by_pot() == sums
    db.close()


def test_deleting_account_cascades_to_pots_and_movements(tmp_path):
    db, accounts, pot_repo, moves = _repos(tmp_path)
    acc_id = accounts.add(SavingsAccount("Konto", balance_cents=10_000))
    pot_id = pot_repo.add(Pot(acc_id, "Urlaub"))
    moves.add(PotMovement(pot_id, "2026-07-01", 1_000))

    accounts.delete(acc_id)
    assert pot_repo.list() == []
    assert moves.sums_by_pot() == {}
    db.close()


def test_linked_goal_takes_balance_from_pot(tmp_path):
    db, accounts, pot_repo, moves = _repos(tmp_path)
    goals = SavingsGoalRepository(db)
    goal_id = goals.add(SavingsGoal("Urlaub", target_cents=100_000,
                                    monthly_cents=10_000, start_date="2026-01-01"))
    acc_id = accounts.add(SavingsAccount("Konto", balance_cents=80_000))
    pot_id = pot_repo.add(Pot(acc_id, "Urlaubs-Topf", goal_id=goal_id))
    moves.add(PotMovement(pot_id, "2026-07-01", 42_000))

    overrides = pots.goal_saved_overrides(pot_repo, moves, today=TODAY)
    assert overrides == {goal_id: 42_000}
    # The goal's progress uses the pot balance, not its own schedule (70.000).
    p = savings_goals.compute(goals.get(goal_id), today=TODAY,
                              saved_override=overrides[goal_id])
    assert p.saved_cents == 42_000
    assert p.remaining_cents == 58_000
    db.close()


def test_wipe_clears_pot_tables(tmp_path):
    db, accounts, pot_repo, moves = _repos(tmp_path)
    acc_id = accounts.add(SavingsAccount("Konto", balance_cents=10_000))
    pot_id = pot_repo.add(Pot(acc_id, "X"))
    moves.add(PotMovement(pot_id, "2026-07-01", 1_000))
    db.wipe_financial_data()
    assert accounts.list() == [] and pot_repo.list() == []
    assert moves.sums_by_pot() == {}
    db.close()

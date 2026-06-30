"""Tests for the savings-plan calculator (rate->result and goal->rate)."""

import pytest

from modules.calculator import savings


def test_from_rate_no_interest():
    res = savings.from_rate(20_000, 12, 0.0, 0)
    assert res.final_cents == 240_000
    assert res.deposited_cents == 240_000
    assert res.interest_cents == 0
    assert res.monthly_cents == 20_000
    assert res.schedule[-1].month == 12


def test_from_rate_with_interest_and_start():
    res = savings.from_rate(20_000, 24, 3.0, 100_000)
    # Balance is always exactly start + deposits + interest.
    assert res.final_cents == 100_000 + res.deposited_cents + res.interest_cents
    assert res.deposited_cents == 24 * 20_000
    assert res.interest_cents > 0
    assert res.final_cents == 601_466          # cent-exact simulation anchor


def test_final_equals_contributions_plus_interest_invariant():
    res = savings.from_rate(15_000, 50, 4.0, 30_000)
    assert res.final_cents == res.start_cents + res.deposited_cents + res.interest_cents


def test_schedule_has_yearly_milestones_plus_final():
    res = savings.from_rate(10_000, 30, 0.0, 0)
    assert [m.month for m in res.schedule] == [12, 24, 30]


def test_from_goal_no_interest():
    res = savings.from_goal(240_000, 12, 0.0, 0)
    assert res.monthly_cents == 20_000
    assert res.final_cents >= 240_000


def test_from_goal_with_interest_meets_goal():
    res = savings.from_goal(1_000_000, 24, 3.0, 0)
    assert res.final_cents >= 1_000_000        # goal is always reached (or just over)
    assert res.monthly_cents == 40_381         # solved rate, cent-exact


def test_from_goal_reached_by_start_capital():
    res = savings.from_goal(500_000, 36, 2.0, 600_000)
    assert res.goal_reached_by_start is True
    assert res.monthly_cents == 0
    assert res.final_cents >= 500_000


def test_invalid_months_raise():
    with pytest.raises(ValueError):
        savings.from_rate(10_000, 0)
    with pytest.raises(ValueError):
        savings.from_goal(10_000, 0)

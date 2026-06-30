"""Tests for the balloon-loan engine and the standard-vs-balloon comparison."""

import pytest

from modules.calculator import annuity, balloon


def test_balloon_zero_equals_annuity():
    # With no balloon the instalment must equal the plain annuity payment.
    p, rate, n = 3_000_000, 5.0, 48
    assert balloon.balloon_payment(p, 0, rate, n) == annuity.monthly_payment(p, rate, n)


def test_balloon_lower_than_standard():
    p, b, rate, n = 3_000_000, 1_000_000, 5.0, 48
    res = balloon.compute(p, b, rate, n)
    std = annuity.monthly_payment(p, rate, n)
    # A balloon keeps the monthly instalment below the fully amortising one.
    assert res.monthly_payment_cents < std


def test_balloon_schedule_ends_at_balloon():
    p, b, rate, n = 2_500_000, 800_000, 4.0, 36
    res = balloon.compute(p, b, rate, n)
    assert res.schedule[-1].balance_cents == b
    # total paid = instalments + balloon = principal + interest
    assert res.total_paid_cents == res.principal_cents + res.total_interest_cents


def test_recommended_reserve():
    p, b, rate, n = 2_000_000, 1_200_000, 3.0, 48
    res = balloon.compute(p, b, rate, n)
    assert res.recommended_reserve_cents == b // n   # 25000, divides evenly
    assert res.effective_monthly_cents == res.monthly_payment_cents + res.recommended_reserve_cents


def test_reserve_rounds_up_to_cover_balloon():
    import math
    # Non-divisible balloon: the reserve must round UP so n*reserve >= balloon —
    # the saver has to reach the final payment, not fall a cent short.
    p, b, n = 2_000_000, 1_000_000, 7
    res = balloon.compute(p, b, 3.0, n)
    assert res.recommended_reserve_cents == math.ceil(b / n)   # 142858, not 142857
    assert res.recommended_reserve_cents * n >= b


def test_comparison():
    p, b, rate, n = 3_000_000, 1_000_000, 6.0, 60
    cmp = balloon.compare(p, b, rate, n)
    # Balloon pays more interest overall but a lower monthly instalment.
    assert cmp.monthly_saving_cents > 0
    assert cmp.extra_interest_cents > 0
    assert cmp.total_balloon_cents > cmp.total_standard_cents


def test_invalid_balloon():
    with pytest.raises(ValueError):
        balloon.balloon_payment(1_000_000, 2_000_000, 5.0, 36)  # balloon > principal


def test_build_schedule_guards():
    # build_schedule must reject an impossible balloon even with explicit payment.
    with pytest.raises(ValueError):
        balloon.build_schedule(1_000_000, 2_000_000, 5.0, 12, payment_cents=5_000)


def test_extreme_balloon_no_negative_final_row():
    # Balloon almost equal to principal over a long term: the final row must not
    # go negative or pay less than its own interest, and must still end at balloon.
    res = balloon.compute(500_000, 495_000, 5.0, 120)
    last = res.schedule[-1]
    assert last.principal_cents >= 0
    assert last.payment_cents >= last.interest_cents
    assert last.balance_cents == 495_000
    assert res.total_paid_cents == res.principal_cents + res.total_interest_cents

"""Tests for the annuity engine.

Anchored on a well-known external reference: a 100,000 loan at 6% nominal
annual interest over 360 months has a monthly payment of 599.55 (the classic
"$599.55 per $100k at 6% / 30y" mortgage figure). Beyond that we assert the
strong amortisation invariants: principal parts sum to the loan and the final
balance is exactly zero.
"""

import pytest

from modules.calculator import annuity


def test_reference_mortgage_payment():
    # 100,000.00 € at 6% over 360 months -> 599.55 €/month
    pay = annuity.monthly_payment(10_000_000, 6.0, 360)
    assert abs(pay - 59_955) <= 2


def test_zero_interest():
    pay = annuity.monthly_payment(1_200_000, 0.0, 24)
    assert pay == 50_000
    res = annuity.compute(1_200_000, 0.0, 24)
    assert res.total_interest_cents == 0
    assert res.total_paid_cents == 1_200_000


def test_schedule_invariants():
    res = annuity.compute(2_543_000, 4.5, 48)
    # Principal parts sum to the loan; final balance is zero.
    assert sum(r.principal_cents for r in res.schedule) == 2_543_000
    assert res.schedule[-1].balance_cents == 0
    # total paid = principal + interest, and matches the row sum.
    assert res.total_paid_cents == res.principal_cents + res.total_interest_cents
    assert res.total_paid_cents == sum(r.payment_cents for r in res.schedule)
    # Every row: payment = interest + principal.
    for r in res.schedule:
        assert r.payment_cents == r.interest_cents + r.principal_cents


def test_interest_decreases_principal_increases():
    res = annuity.compute(5_000_000, 5.0, 60)
    interests = [r.interest_cents for r in res.schedule]
    principals = [r.principal_cents for r in res.schedule]
    # Interest portion shrinks, principal portion grows over the term.
    assert interests[0] > interests[-1]
    assert principals[0] < principals[-1]


def test_solve_term_and_principal_roundtrip():
    principal, rate, term = 3_000_000, 7.0, 72
    pay = annuity.monthly_payment(principal, rate, term)
    # Recover the term from the payment.
    solved_term = annuity.solve_term_months(principal, pay, rate)
    assert abs(solved_term - term) <= 1
    # Recover the principal from the payment.
    solved_principal = annuity.solve_principal(pay, rate, term)
    assert abs(solved_principal - principal) <= 100  # within 1 €


def test_payment_too_low_to_amortise():
    with pytest.raises(ValueError):
        # 10 €/month on 100,000 € at 10% never covers the interest.
        annuity.solve_term_months(10_000_000, 1_000, 10.0)

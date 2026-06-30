"""Savings-plan calculator.

Two directions, both in integer cents and with optional compound interest and a
starting capital:

* :func:`from_rate` — given a monthly savings rate and a term, project the final
  amount, the total paid in and the interest earned.
* :func:`from_goal` — given a target amount and a term, solve the monthly rate
  needed to reach it.

Interest convention (monthly compounding): each month the rate is paid in at the
start of the month and the whole balance then earns one month of interest
(annual rate / 12). The result is computed by a month-by-month simulation so the
displayed figures match the cent-exact schedule rather than a float formula.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.money import round_half_up


@dataclass
class SavingsMilestone:
    month: int
    deposited_cents: int      # cumulative deposits over the term (excl. start)
    interest_cents: int       # cumulative interest
    balance_cents: int        # total balance incl. the starting capital


@dataclass
class SavingsResult:
    months: int
    monthly_cents: int            # the savings rate (solved one for from_goal)
    start_cents: int
    annual_rate_pct: float
    final_cents: int              # balance at the end of the term
    deposited_cents: int          # total paid in over the term (excl. start)
    interest_cents: int           # total interest earned
    goal_reached_by_start: bool = False   # from_goal: start alone already suffices
    schedule: list = field(default_factory=list)   # yearly milestones + final month


def _simulate(monthly_cents: int, months: int, annual_rate_pct: float,
              start_cents: int) -> tuple[int, int, int, list[SavingsMilestone]]:
    """Month-by-month run; returns (final, deposited, interest, milestones)."""
    monthly_i = annual_rate_pct / 100.0 / 12.0
    balance = start_cents
    deposited = 0
    interest_total = 0
    schedule: list[SavingsMilestone] = []
    for m in range(1, months + 1):
        balance += monthly_cents
        deposited += monthly_cents
        if monthly_i:
            month_interest = round_half_up(balance * monthly_i)
            balance += month_interest
            interest_total += month_interest
        if m % 12 == 0 or m == months:
            schedule.append(SavingsMilestone(m, deposited, interest_total, balance))
    return balance, deposited, interest_total, schedule


def from_rate(monthly_cents: int, months: int, annual_rate_pct: float = 0.0,
              start_cents: int = 0) -> SavingsResult:
    """Project a fixed monthly savings rate over ``months`` to a final amount."""
    if months <= 0:
        raise ValueError("Die Laufzeit muss mindestens 1 Monat betragen.")
    monthly_cents = max(0, int(monthly_cents))
    start_cents = max(0, int(start_cents))
    final, deposited, interest, schedule = _simulate(
        monthly_cents, months, annual_rate_pct, start_cents)
    return SavingsResult(
        months=months, monthly_cents=monthly_cents, start_cents=start_cents,
        annual_rate_pct=annual_rate_pct, final_cents=final, deposited_cents=deposited,
        interest_cents=interest, schedule=schedule)


def from_goal(goal_cents: int, months: int, annual_rate_pct: float = 0.0,
              start_cents: int = 0) -> SavingsResult:
    """Solve the monthly rate needed to reach ``goal_cents`` after ``months``.

    Uses the closed-form annuity-due value as a first guess, then nudges the
    rate up by whole cents and re-simulates until the (cent-exact, rounded)
    balance actually meets the goal. If the starting capital already grows past
    the goal on its own, the required rate is 0.
    """
    if months <= 0:
        raise ValueError("Die Laufzeit muss mindestens 1 Monat betragen.")
    goal_cents = max(0, int(goal_cents))
    start_cents = max(0, int(start_cents))

    # Does the start capital alone already reach the goal?
    grown_start, _dep, _int, _sched = _simulate(0, months, annual_rate_pct, start_cents)
    if grown_start >= goal_cents:
        final, deposited, interest, schedule = _simulate(0, months, annual_rate_pct, start_cents)
        return SavingsResult(
            months=months, monthly_cents=0, start_cents=start_cents,
            annual_rate_pct=annual_rate_pct, final_cents=final, deposited_cents=deposited,
            interest_cents=interest, goal_reached_by_start=True, schedule=schedule)

    # First guess from the annuity-due closed form.
    i = annual_rate_pct / 100.0 / 12.0
    if i > 0:
        factor = (1 + i) ** months
        annuity_due = (1 + i) * (factor - 1) / i   # FV of 1/month, paid at start
        guess = (goal_cents - start_cents * factor) / annuity_due
    else:
        guess = (goal_cents - start_cents) / months
    monthly = max(0, int(guess))   # start at/below; the loop tops it up exactly

    # Top up by whole cents until the simulated balance meets the goal. Bounded
    # by a generous cap so a pathological input can never loop forever.
    for _ in range(months + 5):
        final, deposited, interest, schedule = _simulate(
            monthly, months, annual_rate_pct, start_cents)
        if final >= goal_cents:
            break
        monthly += 1

    return SavingsResult(
        months=months, monthly_cents=monthly, start_cents=start_cents,
        annual_rate_pct=annual_rate_pct, final_cents=final, deposited_cents=deposited,
        interest_cents=interest, schedule=schedule)

"""Töpfe: virtual partitions of real savings accounts (Qt-free).

A bank savings account holds one anonymous lump sum; pots make its composition
visible ("1.000 € = 400 € Urlaub + 250 € Auto + 350 € nicht verteilt"). A pot's
balance is always DERIVED, never stored:

    balance = monthly rate × months since ``rate_start`` (inclusive)
              + sum of its explicit movements

The rate mirrors the user's real standing order ("richte bei deiner Bank einen
Dauerauftrag über dieselbe Rate ein, dann stimmt der Topf von allein");
movements cover everything irregular (Startbestand, Entnahme, Extra-Zahlung,
Umbuchung). The account's recorded balance is compared against the pots' sum,
so money that is not covered by any pot shows up as "nicht verteilt" — and an
over-allocation (pots > account) is flagged instead of silently hidden.

All amounts are integer cents. Nothing here writes to the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from modules import dates


@dataclass(frozen=True)
class PotState:
    """One pot with its derived balance."""

    pot: object                    # models.Pot
    rate_cents: int                # auto part: rate × elapsed months
    moved_cents: int               # signed sum of explicit movements

    @property
    def balance_cents(self) -> int:
        return self.rate_cents + self.moved_cents


@dataclass
class AccountOverview:
    """One savings account with its pots and the allocation check."""

    account: object                # models.SavingsAccount
    pots: list = field(default_factory=list)   # list[PotState]

    @property
    def allocated_cents(self) -> int:
        return sum(p.balance_cents for p in self.pots)

    @property
    def unallocated_cents(self) -> int:
        """Account balance not covered by any pot (negative = over-allocated,
        i.e. the pots promise more money than the account actually holds)."""
        return self.account.balance_cents - self.allocated_cents


def rate_part(pot, today: date | None = None) -> int:
    """The automatic share of a pot's balance: rate × months since start.

    The start month itself counts (the standing order runs in it); a future
    start or a missing/unparseable date contributes nothing yet.
    """
    monthly = max(0, int(pot.monthly_cents or 0))
    if monthly <= 0:
        return 0
    start = dates.parse_date(pot.rate_start) if pot.rate_start else None
    if start is None:
        return 0
    today = today or date.today()
    elapsed = (today.year - start.year) * 12 + (today.month - start.month) + 1
    return monthly * max(0, elapsed)


def build_overview(account_repo, pot_repo, move_repo,
                   today: date | None = None) -> list[AccountOverview]:
    """All accounts with their pots' derived balances (creation order)."""
    today = today or date.today()
    sums = move_repo.sums_by_pot()
    out: list[AccountOverview] = []
    for account in account_repo.list():
        states = [PotState(pot=p, rate_cents=rate_part(p, today),
                           moved_cents=sums.get(p.id, 0))
                  for p in pot_repo.list_for_account(account.id)]
        out.append(AccountOverview(account=account, pots=states))
    return out


def goal_saved_overrides(pot_repo, move_repo,
                         today: date | None = None) -> dict[int, int]:
    """Map goal_id -> pot balance for every pot linked to a Sparziel.

    A linked goal shows the POT's real balance as its saved amount instead of
    its own schedule estimate — the pot is the source of truth then.
    """
    today = today or date.today()
    sums = move_repo.sums_by_pot()
    out: dict[int, int] = {}
    for pot in pot_repo.list():
        if pot.goal_id is not None:
            out[pot.goal_id] = rate_part(pot, today) + sums.get(pot.id, 0)
    return out

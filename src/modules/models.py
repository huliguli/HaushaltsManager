"""Domain model dataclasses and shared category definitions.

These mirror the SQLite tables. Money fields are always integer cents.
Each model knows how to build itself from a ``sqlite3.Row`` and back to a
parameter dict, keeping SQL out of the rest of the application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from modules import dates

# --- Shared category vocabularies -----------------------------------------
# Used to populate dropdowns and to colour-code the UI consistently.
FIXED_CATEGORIES = [
    "Wohnen", "Auto", "Kommunikation", "Kredit",
    "Freizeit", "Persönlich", "Versicherung", "Sparen", "Sonstiges",
]
# Expense taxonomy (schema v2). Order = dropdown display order, everyday
# spending first, the "Sonstiges" fallback last. These strings are the single
# source of truth: the bank-import categoriser (modules.bank_import.seed_rules)
# may only emit names from this list, and the v2 DB migration maps the old short
# names onto them — a guard test asserts both invariants.
EXPENSE_CATEGORIES = [
    "Lebensmittel",
    "Essen Bestellen & Fast Food",
    "Restaurant & Café",
    "Auto & Tanken",
    "Mobilität & ÖPNV",
    "Energie & Nebenkosten",
    "Telekommunikation",
    "Streaming & Abos",
    "Versicherung",
    "Finanzen & Gebühren",
    "Drogerie & Körperpflege",
    "Gesundheit & Apotheke",
    "Kleidung & Mode",
    "Elektronik & Technik",
    "Haushalt & Möbel",
    "Freizeit & Unterhaltung",
    "Reisen & Urlaub",
    "Bildung",
    "Kinder & Familie",
    "Spenden",
    "Shopping & Online",
    "Wohnen & Miete",
    "Bargeld",
    "Sonstiges",
]
CREDIT_CATEGORIES = ["Auto", "Haus", "Divers", "Persönlich"]
INCOME_TYPES = ["minijob", "teilzeit", "vollzeit", "sonstiges"]
INCOME_TYPE_LABELS = {
    "minijob": "Minijob",
    "teilzeit": "Teilzeit",
    "vollzeit": "Vollzeit",
    "sonstiges": "Sonstiges",
}
CREDIT_STATUS = ["aktiv", "abbezahlt", "pausiert"]
CREDIT_STATUS_LABELS = {
    "aktiv": "Aktiv",
    "abbezahlt": "Abbezahlt",
    "pausiert": "Pausiert",
}


@dataclass
class IncomeSource:
    name: str
    amount_cents: int = 0
    income_type: str = "sonstiges"
    active: bool = True
    note: str = ""
    id: int | None = None

    @staticmethod
    def from_row(row) -> "IncomeSource":
        return IncomeSource(
            id=row["id"],
            name=row["name"],
            amount_cents=row["amount_cents"],
            income_type=row["income_type"],
            active=bool(row["active"]),
            note=row["note"] or "",
        )

    def to_params(self) -> dict:
        return {
            "name": self.name,
            "amount_cents": int(self.amount_cents),
            "income_type": self.income_type,
            "active": 1 if self.active else 0,
            "note": self.note or None,
        }


@dataclass
class FixedCost:
    name: str
    amount_cents: int = 0
    category: str = "Sonstiges"
    start_date: str | None = None     # ISO
    end_date: str | None = None       # ISO, None = open-ended
    note: str = ""
    active: bool = True
    id: int | None = None

    @staticmethod
    def from_row(row) -> "FixedCost":
        return FixedCost(
            id=row["id"],
            name=row["name"],
            amount_cents=row["amount_cents"],
            category=row["category"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            note=row["note"] or "",
            active=bool(row["active"]),
        )

    def to_params(self) -> dict:
        return {
            "name": self.name,
            "amount_cents": int(self.amount_cents),
            "category": self.category,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "note": self.note or None,
            "active": 1 if self.active else 0,
        }

    def months_remaining(self, frm: date | None = None) -> int | None:
        return dates.months_remaining(self.end_date, frm)

    def status_key(self, frm: date | None = None) -> str:
        """Traffic-light status used for colour coding.

        green  <= 6 months remaining (about to drop off)
        amber  6-24 months remaining
        grey   open-ended (no end date)
        red    already overdue / ended
        """
        m = self.months_remaining(frm)
        if m is None:
            return "grey"
        if m < 0:
            return "red"
        if m <= 6:
            return "green"
        if m <= 24:
            return "amber"
        return "grey"


@dataclass
class VariableExpense:
    date: str                          # ISO (for a recurring item: its start month)
    amount_cents: int = 0
    category: str = "Sonstiges"
    description: str = ""
    receipt_path: str | None = None
    recurring: bool = False            # True = recurring template
    interval_months: int = 1           # cadence: 1 monthly, 3 quarterly, 12 yearly
    recur_end: str | None = None       # optional ISO date the recurrence stops at
    id: int | None = None

    # UI vocabulary for the cadence — single source for dialog and table marker.
    INTERVAL_LABELS = {1: "monatlich", 3: "quartalsweise", 12: "jährlich"}

    def interval_label(self) -> str:
        return self.INTERVAL_LABELS.get(
            self.interval_months, f"alle {self.interval_months} Monate")

    @staticmethod
    def from_row(row) -> "VariableExpense":
        keys = row.keys()
        return VariableExpense(
            id=row["id"],
            date=row["date"],
            amount_cents=row["amount_cents"],
            category=row["category"],
            description=row["description"] or "",
            receipt_path=row["receipt_path"],
            recurring=bool(row["recurring"]),
            # Defensive: rows read from a pre-v4 snapshot (e.g. a backup file
            # inspected read-only, before any migration ran) lack the columns.
            interval_months=int(row["recur_interval_months"])
            if "recur_interval_months" in keys else 1,
            recur_end=row["recur_end"] if "recur_end" in keys else None,
        )

    def to_params(self) -> dict:
        return {
            "date": self.date,
            "amount_cents": int(self.amount_cents),
            "category": self.category,
            "description": self.description or None,
            "receipt_path": self.receipt_path,
            "recurring": 1 if self.recurring else 0,
            "recur_interval_months": max(1, int(self.interval_months)),
            "recur_end": self.recur_end,
        }


@dataclass
class VariableIncome:
    """One-off, dated income (e.g. an imported bank credit).

    Counts only in its own month — never as recurring monthly income.
    """

    date: str                          # ISO YYYY-MM-DD
    amount_cents: int = 0
    source: str = ""
    id: int | None = None

    @staticmethod
    def from_row(row) -> "VariableIncome":
        return VariableIncome(
            id=row["id"],
            date=row["date"],
            amount_cents=row["amount_cents"],
            source=row["source"] or "",
        )

    def to_params(self) -> dict:
        return {
            "date": self.date,
            "amount_cents": int(self.amount_cents),
            "source": self.source or None,
        }


@dataclass
class Credit:
    name: str
    total_cents: int | None = None
    monthly_cents: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    term_months: int | None = None
    interest_rate: float | None = None
    category: str = "Divers"
    note: str = ""
    status: str = "aktiv"
    linked_fixed_cost_id: int | None = None
    id: int | None = None

    @staticmethod
    def from_row(row) -> "Credit":
        return Credit(
            id=row["id"],
            name=row["name"],
            total_cents=row["total_cents"],
            monthly_cents=row["monthly_cents"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            term_months=row["term_months"],
            interest_rate=row["interest_rate"],
            category=row["category"],
            note=row["note"] or "",
            status=row["status"],
            linked_fixed_cost_id=row["linked_fixed_cost_id"],
        )

    def to_params(self) -> dict:
        return {
            "name": self.name,
            "total_cents": self.total_cents,
            "monthly_cents": self.monthly_cents,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "term_months": self.term_months,
            "interest_rate": self.interest_rate,
            "category": self.category,
            "note": self.note or None,
            "status": self.status,
            "linked_fixed_cost_id": self.linked_fixed_cost_id,
        }


@dataclass
class SavingsGoal:
    """A persisted savings target whose progress is derived, never booked.

    The saved amount is the scheduled state (``monthly_cents`` × months since
    ``start_date``, see :mod:`modules.savings_goals`) plus ``manual_cents`` — a
    user correction for an existing start balance or a skipped month. This
    keeps the goal honest without a separate bookings table.
    """

    name: str
    target_cents: int = 0
    monthly_cents: int = 0
    start_date: str | None = None      # ISO; first month that counts as saved
    manual_cents: int = 0              # correction, may be negative
    note: str = ""
    id: int | None = None

    @staticmethod
    def from_row(row) -> "SavingsGoal":
        return SavingsGoal(
            id=row["id"],
            name=row["name"],
            target_cents=row["target_cents"],
            monthly_cents=row["monthly_cents"],
            start_date=row["start_date"],
            manual_cents=row["manual_cents"],
            note=row["note"] or "",
        )

    def to_params(self) -> dict:
        return {
            "name": self.name,
            "target_cents": int(self.target_cents),
            "monthly_cents": int(self.monthly_cents),
            # The column is NOT NULL: a goal without an explicit start simply
            # starts counting in the month it was created.
            "start_date": self.start_date or dates.to_iso(dates.today()),
            "manual_cents": int(self.manual_cents),
            "note": self.note or None,
        }


@dataclass
class SavingsAccount:
    """A real savings account whose balance the pots partition virtually."""

    name: str
    balance_cents: int = 0             # zuletzt erfasster Kontostand
    balance_date: str | None = None    # ISO; wann erfasst
    note: str = ""
    id: int | None = None

    @staticmethod
    def from_row(row) -> "SavingsAccount":
        return SavingsAccount(
            id=row["id"], name=row["name"], balance_cents=row["balance_cents"],
            balance_date=row["balance_date"], note=row["note"] or "")

    def to_params(self) -> dict:
        return {
            "name": self.name,
            "balance_cents": int(self.balance_cents),
            "balance_date": self.balance_date or dates.to_iso(dates.today()),
            "note": self.note or None,
        }


@dataclass
class Pot:
    """A virtual partition ("Topf") of a savings account.

    The balance is derived, never stored: monthly rate × months since
    ``rate_start`` (mirrors the user's real standing order) plus the sum of
    explicit movements — see :mod:`modules.pots`.
    """

    account_id: int
    name: str
    monthly_cents: int = 0             # Rate; 0 = wächst nur durch Buchungen
    rate_start: str | None = None      # ISO; erster Monat, der zählt
    goal_id: int | None = None         # optional verknüpftes Sparziel
    note: str = ""
    id: int | None = None

    @staticmethod
    def from_row(row) -> "Pot":
        return Pot(
            id=row["id"], account_id=row["account_id"], name=row["name"],
            monthly_cents=row["monthly_cents"], rate_start=row["rate_start"],
            goal_id=row["goal_id"], note=row["note"] or "")

    def to_params(self) -> dict:
        return {
            "account_id": int(self.account_id),
            "name": self.name,
            "monthly_cents": max(0, int(self.monthly_cents)),
            "rate_start": self.rate_start,
            "goal_id": self.goal_id,
            "note": self.note or None,
        }


@dataclass
class PotMovement:
    """One explicit pot booking: + Einzahlung, − Entnahme (signed cents)."""

    pot_id: int
    date: str                          # ISO YYYY-MM-DD
    amount_cents: int
    note: str = ""
    id: int | None = None

    @staticmethod
    def from_row(row) -> "PotMovement":
        return PotMovement(
            id=row["id"], pot_id=row["pot_id"], date=row["date"],
            amount_cents=row["amount_cents"], note=row["note"] or "")

    def to_params(self) -> dict:
        return {
            "pot_id": int(self.pot_id),
            "date": self.date,
            "amount_cents": int(self.amount_cents),
            "note": self.note or None,
        }


@dataclass
class MonthlySummary:
    year: int
    month: int
    income_cents: int = 0
    fixed_cents: int = 0
    variable_cents: int = 0
    remaining_cents: int = 0
    note: str = ""
    id: int | None = None


@dataclass
class CategoryBudget:
    """Optional monthly spending target (integer cents) for one expense category."""

    category: str
    limit_cents: int = 0
    id: int | None = None

    @staticmethod
    def from_row(row) -> "CategoryBudget":
        return CategoryBudget(
            id=row["id"],
            category=row["category"],
            limit_cents=row["limit_cents"],
        )


@dataclass
class BudgetOverview:
    """Computed snapshot for the dashboard (not persisted directly)."""

    income_cents: int = 0             # this month: recurring + one-off income
    recurring_income_cents: int = 0   # recurring only — use for FUTURE projections
    fixed_cents: int = 0
    variable_cents: int = 0
    credits_cents: int = 0            # share of fixed that are loan instalments
    expenses_by_category: dict = field(default_factory=dict)

    @property
    def after_fixed_cents(self) -> int:
        """Disposable income once fixed costs are covered."""
        return self.income_cents - self.fixed_cents

    @property
    def after_all_cents(self) -> int:
        """Disposable income after fixed *and* variable spending."""
        return self.income_cents - self.fixed_cents - self.variable_cents

    @property
    def recurring_after_fixed_cents(self) -> int:
        """Like :attr:`after_fixed_cents` but on the *recurring* income only.

        Use this for long-term / repeating decisions (annual projections, car or
        savings feasibility): a one-off credit booked this month must not lift a
        budget that is meant to hold every month.
        """
        return self.recurring_income_cents - self.fixed_cents

    @property
    def recurring_after_all_cents(self) -> int:
        """Recurring income minus fixed *and* this month's variable spending."""
        return self.recurring_income_cents - self.fixed_cents - self.variable_cents

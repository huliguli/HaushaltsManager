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
    "Freizeit", "Persönlich", "Versicherung", "Sonstiges",
]
EXPENSE_CATEGORIES = [
    "Lebensmittel", "Tanken", "Freizeit", "Kleidung",
    "Drogerie", "Gesundheit", "Haushalt", "Sonstiges",
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
    recurring: bool = False            # True = monthly-recurring template
    id: int | None = None

    @staticmethod
    def from_row(row) -> "VariableExpense":
        return VariableExpense(
            id=row["id"],
            date=row["date"],
            amount_cents=row["amount_cents"],
            category=row["category"],
            description=row["description"] or "",
            receipt_path=row["receipt_path"],
            recurring=bool(row["recurring"]),
        )

    def to_params(self) -> dict:
        return {
            "date": self.date,
            "amount_cents": int(self.amount_cents),
            "category": self.category,
            "description": self.description or None,
            "receipt_path": self.receipt_path,
            "recurring": 1 if self.recurring else 0,
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
class BudgetOverview:
    """Computed snapshot for the dashboard (not persisted directly)."""

    income_cents: int = 0
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

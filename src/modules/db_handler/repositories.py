"""Repositories: typed CRUD + aggregate queries over the database.

Each repository returns/accepts the dataclasses from ``modules.models`` so the
UI never touches SQL or raw rows. All queries are parameterised.
"""

from __future__ import annotations

from modules.db_handler.database import Database
from modules.models import (
    Credit,
    FixedCost,
    IncomeSource,
    MonthlySummary,
    VariableExpense,
)


class IncomeRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self, only_active: bool = False) -> list[IncomeSource]:
        sql = "SELECT * FROM income_sources"
        if only_active:
            sql += " WHERE active = 1"
        sql += " ORDER BY active DESC, amount_cents DESC, name"
        return [IncomeSource.from_row(r) for r in self.db.query(sql)]

    def get(self, row_id: int) -> IncomeSource | None:
        row = self.db.query_one("SELECT * FROM income_sources WHERE id = ?", (row_id,))
        return IncomeSource.from_row(row) if row else None

    def add(self, item: IncomeSource) -> int:
        return self.db.insert("income_sources", item.to_params())

    def update(self, item: IncomeSource) -> None:
        if item.id is None:
            raise ValueError("IncomeSource ohne id kann nicht aktualisiert werden.")
        self.db.update("income_sources", item.id, item.to_params())

    def delete(self, row_id: int) -> None:
        self.db.delete("income_sources", row_id)

    def total_active(self) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total "
            "FROM income_sources WHERE active = 1"
        )
        return int(row["total"]) if row else 0


class FixedCostRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self, only_active: bool = True) -> list[FixedCost]:
        sql = "SELECT * FROM fixed_costs"
        if only_active:
            sql += " WHERE active = 1"
        sql += " ORDER BY amount_cents DESC, name"
        return [FixedCost.from_row(r) for r in self.db.query(sql)]

    def get(self, row_id: int) -> FixedCost | None:
        row = self.db.query_one("SELECT * FROM fixed_costs WHERE id = ?", (row_id,))
        return FixedCost.from_row(row) if row else None

    def add(self, item: FixedCost) -> int:
        return self.db.insert("fixed_costs", item.to_params())

    def update(self, item: FixedCost) -> None:
        if item.id is None:
            raise ValueError("FixedCost ohne id kann nicht aktualisiert werden.")
        self.db.update("fixed_costs", item.id, item.to_params())

    def delete(self, row_id: int) -> None:
        self.db.delete("fixed_costs", row_id)

    def active_for_month(self, month_start: str, month_end: str) -> list[FixedCost]:
        """Fixed costs effective during a calendar month (ISO date strings).

        ISO date strings compare correctly lexicographically.
        """
        sql = (
            "SELECT * FROM fixed_costs WHERE active = 1 "
            "AND (start_date IS NULL OR start_date <= ?) "
            "AND (end_date   IS NULL OR end_date   >= ?) "
            "ORDER BY amount_cents DESC, name"
        )
        rows = self.db.query(sql, (month_end, month_start))
        return [FixedCost.from_row(r) for r in rows]

    def total_active(self) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total "
            "FROM fixed_costs WHERE active = 1"
        )
        return int(row["total"]) if row else 0


class VariableExpenseRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_for_range(self, start_iso: str, end_iso: str) -> list[VariableExpense]:
        rows = self.db.query(
            "SELECT * FROM variable_expenses WHERE date >= ? AND date <= ? "
            "ORDER BY date DESC, id DESC",
            (start_iso, end_iso),
        )
        return [VariableExpense.from_row(r) for r in rows]

    def list_recent(self, limit: int = 200) -> list[VariableExpense]:
        rows = self.db.query(
            "SELECT * FROM variable_expenses ORDER BY date DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [VariableExpense.from_row(r) for r in rows]

    def get(self, row_id: int) -> VariableExpense | None:
        row = self.db.query_one("SELECT * FROM variable_expenses WHERE id = ?", (row_id,))
        return VariableExpense.from_row(row) if row else None

    def add(self, item: VariableExpense) -> int:
        return self.db.insert("variable_expenses", item.to_params())

    def update(self, item: VariableExpense) -> None:
        if item.id is None:
            raise ValueError("VariableExpense ohne id kann nicht aktualisiert werden.")
        self.db.update("variable_expenses", item.id, item.to_params())

    def delete(self, row_id: int) -> None:
        self.db.delete("variable_expenses", row_id)

    def total_for_range(self, start_iso: str, end_iso: str) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM variable_expenses "
            "WHERE date >= ? AND date <= ?",
            (start_iso, end_iso),
        )
        return int(row["total"]) if row else 0

    def by_category_for_range(self, start_iso: str, end_iso: str) -> dict[str, int]:
        rows = self.db.query(
            "SELECT category, COALESCE(SUM(amount_cents), 0) AS total "
            "FROM variable_expenses WHERE date >= ? AND date <= ? "
            "GROUP BY category ORDER BY total DESC",
            (start_iso, end_iso),
        )
        return {r["category"]: int(r["total"]) for r in rows}

    def monthly_totals(self, months: int = 12) -> list[tuple[str, int]]:
        """(YYYY-MM, total_cents) for the most recent ``months`` months present."""
        rows = self.db.query(
            "SELECT substr(date, 1, 7) AS ym, COALESCE(SUM(amount_cents), 0) AS total "
            "FROM variable_expenses GROUP BY ym ORDER BY ym DESC LIMIT ?",
            (months,),
        )
        return [(r["ym"], int(r["total"])) for r in reversed(rows)]


class CreditRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self) -> list[Credit]:
        rows = self.db.query(
            "SELECT * FROM credits ORDER BY "
            "CASE status WHEN 'aktiv' THEN 0 WHEN 'pausiert' THEN 1 ELSE 2 END, name"
        )
        return [Credit.from_row(r) for r in rows]

    def get(self, row_id: int) -> Credit | None:
        row = self.db.query_one("SELECT * FROM credits WHERE id = ?", (row_id,))
        return Credit.from_row(row) if row else None

    def add(self, item: Credit) -> int:
        return self.db.insert("credits", item.to_params())

    def update(self, item: Credit) -> None:
        if item.id is None:
            raise ValueError("Credit ohne id kann nicht aktualisiert werden.")
        self.db.update("credits", item.id, item.to_params())

    def delete(self, row_id: int) -> None:
        self.db.delete("credits", row_id)


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


class MonthlySummaryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert(self, s: MonthlySummary) -> None:
        self.db.execute(
            "INSERT INTO monthly_summary "
            "(year, month, income_cents, fixed_cents, variable_cents, remaining_cents, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(year, month) DO UPDATE SET "
            "income_cents=excluded.income_cents, fixed_cents=excluded.fixed_cents, "
            "variable_cents=excluded.variable_cents, remaining_cents=excluded.remaining_cents, "
            "note=excluded.note",
            (s.year, s.month, s.income_cents, s.fixed_cents,
             s.variable_cents, s.remaining_cents, s.note or None),
        )

    def list(self, limit: int = 24) -> list[MonthlySummary]:
        rows = self.db.query(
            "SELECT * FROM monthly_summary ORDER BY year DESC, month DESC LIMIT ?",
            (limit,),
        )
        return [
            MonthlySummary(
                id=r["id"], year=r["year"], month=r["month"],
                income_cents=r["income_cents"], fixed_cents=r["fixed_cents"],
                variable_cents=r["variable_cents"], remaining_cents=r["remaining_cents"],
                note=r["note"] or "",
            )
            for r in rows
        ]

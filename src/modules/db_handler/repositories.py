"""Repositories: typed CRUD + aggregate queries over the database.

Each repository returns/accepts the dataclasses from ``modules.models`` so the
UI never touches SQL or raw rows. All queries are parameterised.
"""

from __future__ import annotations

from modules.db_handler.database import Database
from modules.models import (
    CategoryBudget,
    Credit,
    FixedCost,
    IncomeSource,
    MonthlySummary,
    VariableExpense,
    VariableIncome,
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
        """One-off (non-recurring) expenses dated within the range."""
        rows = self.db.query(
            "SELECT * FROM variable_expenses WHERE recurring = 0 "
            "AND date >= ? AND date <= ? ORDER BY date DESC, id DESC",
            (start_iso, end_iso),
        )
        return [VariableExpense.from_row(r) for r in rows]

    # -- monthly view (one-off expenses + recurring occurrences) ------------
    @staticmethod
    def _month_bounds(year: int, month: int) -> tuple[str, str, int]:
        import calendar
        last = calendar.monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}", last

    def _recurring_occurrences(self, year: int, month: int) -> list[VariableExpense]:
        """Recurring templates whose cadence hits (year, month), each returned
        as a virtual expense dated within that month (day clamped to its length).

        A template recurs every ``interval_months`` (1 monthly, 3 quarterly,
        12 yearly) starting from its own month; an optional ``recur_end`` is
        the last date an occurrence may fall on. The returned occurrence keeps
        the template's ``id`` so edit/delete in the UI act on the template
        (i.e. on every month at once).
        """
        _start, end, last = self._month_bounds(year, month)
        rows = self.db.query(
            "SELECT * FROM variable_expenses WHERE recurring = 1 AND date <= ? ORDER BY id",
            (end,),
        )
        out: list[VariableExpense] = []
        for r in rows:
            t = VariableExpense.from_row(r)
            interval = max(1, t.interval_months)
            try:
                months_since = ((year - int(t.date[:4])) * 12
                                + (month - int(t.date[5:7])))
                day = min(int(t.date[8:10]), last)
            except (ValueError, IndexError):
                months_since, day = 0, 1
            if months_since % interval:
                continue  # this month is between two occurrences
            occurrence_date = f"{year:04d}-{month:02d}-{day:02d}"
            if t.recur_end and occurrence_date > t.recur_end:
                continue  # the recurrence has ended
            out.append(VariableExpense(
                id=t.id, date=occurrence_date, amount_cents=t.amount_cents,
                category=t.category, description=t.description, receipt_path=t.receipt_path,
                recurring=True, interval_months=t.interval_months, recur_end=t.recur_end))
        return out

    def list_for_month(self, year: int, month: int) -> list[VariableExpense]:
        start, end, _ = self._month_bounds(year, month)
        items = self.list_for_range(start, end) + self._recurring_occurrences(year, month)
        items.sort(key=lambda e: (e.date, e.id or 0), reverse=True)
        return items

    def recurring_total_for_month(self, year: int, month: int) -> int:
        """Sum of the recurring occurrences hitting (year, month) — also valid
        for FUTURE months, which is what the forecast projection builds on."""
        return sum(o.amount_cents for o in self._recurring_occurrences(year, month))

    def total_for_month(self, year: int, month: int) -> int:
        start, end, _ = self._month_bounds(year, month)
        recurring = sum(o.amount_cents for o in self._recurring_occurrences(year, month))
        return self.total_for_range(start, end) + recurring

    def by_category_for_month(self, year: int, month: int) -> dict[str, int]:
        start, end, _ = self._month_bounds(year, month)
        agg = dict(self.by_category_for_range(start, end))
        for o in self._recurring_occurrences(year, month):
            agg[o.category] = agg.get(o.category, 0) + o.amount_cents
        return dict(sorted(agg.items(), key=lambda kv: kv[1], reverse=True))

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
            "WHERE recurring = 0 AND date >= ? AND date <= ?",
            (start_iso, end_iso),
        )
        return int(row["total"]) if row else 0

    def by_category_for_range(self, start_iso: str, end_iso: str) -> dict[str, int]:
        rows = self.db.query(
            "SELECT category, COALESCE(SUM(amount_cents), 0) AS total "
            "FROM variable_expenses WHERE recurring = 0 AND date >= ? AND date <= ? "
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


class VariableIncomeRepository:
    """One-off, dated income (e.g. imported bank credits).

    Counts only in its booking month — never recurring, so a single transfer
    cannot inflate the ongoing monthly income.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _month_bounds(year: int, month: int) -> tuple[str, str]:
        import calendar
        last = calendar.monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"

    def add(self, item: VariableIncome) -> int:
        return self.db.insert("variable_income", item.to_params())

    def get(self, row_id: int) -> VariableIncome | None:
        row = self.db.query_one("SELECT * FROM variable_income WHERE id = ?", (row_id,))
        return VariableIncome.from_row(row) if row else None

    def delete(self, row_id: int) -> None:
        self.db.delete("variable_income", row_id)

    def total_for_month(self, year: int, month: int) -> int:
        start, end = self._month_bounds(year, month)
        row = self.db.query_one(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM variable_income "
            "WHERE date >= ? AND date <= ?", (start, end))
        return int(row["total"]) if row else 0

    def list_for_month(self, year: int, month: int) -> list[VariableIncome]:
        start, end = self._month_bounds(year, month)
        rows = self.db.query(
            "SELECT * FROM variable_income WHERE date >= ? AND date <= ? "
            "ORDER BY date DESC, id DESC", (start, end))
        return [VariableIncome.from_row(r) for r in rows]

    def list_recent(self, limit: int = 200) -> list[VariableIncome]:
        rows = self.db.query(
            "SELECT * FROM variable_income ORDER BY date DESC, id DESC LIMIT ?", (limit,))
        return [VariableIncome.from_row(r) for r in rows]


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


class ImportRuleRepository:
    """Learned categorisation rules (payee/purpose pattern -> category)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def rules(self) -> list[tuple[str, str]]:
        """(pattern, category), highest priority first — for the categoriser."""
        rows = self.db.query(
            "SELECT pattern, category FROM import_rules "
            "ORDER BY learned DESC, priority ASC, id ASC")
        return [(r["pattern"], r["category"]) for r in rows]

    def list_full(self) -> list[dict]:
        rows = self.db.query(
            "SELECT id, pattern, category, learned FROM import_rules "
            "ORDER BY category, pattern")
        return [dict(r) for r in rows]

    def upsert(self, pattern: str, category: str, learned: bool = True) -> None:
        pattern = (pattern or "").strip()
        if not pattern:
            return
        self.db.execute(
            "INSERT INTO import_rules (pattern, category, learned) VALUES (?, ?, ?) "
            "ON CONFLICT(pattern) DO UPDATE SET category = excluded.category, "
            "learned = excluded.learned",
            (pattern, category, 1 if learned else 0))

    def delete(self, rule_id: int) -> None:
        self.db.delete("import_rules", rule_id)


class ImportLogRepository:
    """De-dup log: which bank transactions were already imported."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def known(self, hashes: list[str]) -> set[str]:
        """Return the subset of ``hashes`` already present (chunked IN query)."""
        found: set[str] = set()
        for i in range(0, len(hashes), 400):
            chunk = hashes[i:i + 400]
            placeholders = ", ".join("?" for _ in chunk)
            rows = self.db.query(
                f"SELECT tx_hash FROM import_log WHERE tx_hash IN ({placeholders})", chunk)
            found.update(r["tx_hash"] for r in rows)
        return found

    def add(self, tx_hash: str, booking_date: str, amount_cents: int,
            batch_id: str | None = None, created_kind: str | None = None,
            created_row_id: int | None = None) -> None:
        """Log an imported transaction; the batch/created columns make the
        whole import reversible ("Letzten Import rückgängig")."""
        self.db.execute(
            "INSERT OR IGNORE INTO import_log "
            "(tx_hash, booking_date, amount_cents, batch_id, created_kind, created_row_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tx_hash, booking_date, amount_cents, batch_id, created_kind, created_row_id))

    def latest_batch(self) -> tuple[str, int, str] | None:
        """(batch_id, row_count, imported_at) of the newest reversible import.

        Rows from releases before v2.7.0 have no batch_id and are therefore
        not reversible; they are simply skipped here.
        """
        row = self.db.query_one(
            "SELECT batch_id, MAX(imported_at) AS newest FROM import_log "
            "WHERE batch_id IS NOT NULL GROUP BY batch_id "
            "ORDER BY newest DESC, batch_id DESC LIMIT 1")
        if not row or not row["batch_id"]:
            return None
        count = self.db.query_one(
            "SELECT COUNT(*) AS n FROM import_log WHERE batch_id = ?",
            (row["batch_id"],))
        return row["batch_id"], int(count["n"]), str(row["newest"] or "")

    def rows_for_batch(self, batch_id: str) -> list:
        return self.db.query(
            "SELECT * FROM import_log WHERE batch_id = ? ORDER BY id", (batch_id,))

    def delete_batch(self, batch_id: str) -> None:
        """Drop a batch's log rows — incl. their hashes, so the same statement
        can be imported again after an undo."""
        self.db.execute("DELETE FROM import_log WHERE batch_id = ?", (batch_id,))


class BankProfileRepository:
    """Saved CSV column mappings, keyed by a user-chosen profile name."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def list_names(self) -> list[str]:
        return [r["name"] for r in self.db.query(
            "SELECT name FROM bank_profiles ORDER BY name")]

    def get(self, name: str) -> str | None:
        row = self.db.query_one(
            "SELECT mapping_json FROM bank_profiles WHERE name = ?", (name,))
        return row["mapping_json"] if row else None

    def list_full(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT id, name FROM bank_profiles ORDER BY name")]

    def upsert(self, name: str, mapping_json: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        self.db.execute(
            "INSERT INTO bank_profiles (name, mapping_json) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET mapping_json = excluded.mapping_json",
            (name, mapping_json))

    def delete(self, profile_id: int) -> None:
        self.db.delete("bank_profiles", profile_id)


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


class CategoryBudgetRepository:
    """Optional monthly spending target per expense category (integer cents)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> dict[str, int]:
        """Map category -> limit_cents for every category that has a budget set."""
        rows = self.db.query(
            "SELECT category, limit_cents FROM category_budgets WHERE limit_cents > 0")
        return {r["category"]: int(r["limit_cents"]) for r in rows}

    def list(self) -> list[CategoryBudget]:
        rows = self.db.query("SELECT * FROM category_budgets ORDER BY category")
        return [CategoryBudget.from_row(r) for r in rows]

    def set(self, category: str, limit_cents: int) -> None:
        """Set (or clear, when ``limit_cents <= 0``) the budget for a category."""
        category = (category or "").strip()
        if not category:
            return
        if limit_cents <= 0:
            self.db.execute(
                "DELETE FROM category_budgets WHERE category = ?", (category,))
            return
        self.db.execute(
            "INSERT INTO category_budgets (category, limit_cents) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET limit_cents = excluded.limit_cents, "
            "updated_at = datetime('now')",
            (category, int(limit_cents)))


class MonthlySummaryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, year: int, month: int) -> MonthlySummary | None:
        row = self.db.query_one(
            "SELECT * FROM monthly_summary WHERE year = ? AND month = ?", (year, month))
        if row is None:
            return None
        return MonthlySummary(
            id=row["id"], year=row["year"], month=row["month"],
            income_cents=row["income_cents"], fixed_cents=row["fixed_cents"],
            variable_cents=row["variable_cents"], remaining_cents=row["remaining_cents"],
            note=row["note"] or "")

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

"""Seed loader: populate an empty database from a JSON file.

Two seed files may exist in the ``database`` folder:
    * ``seed.local.json``  — the user's REAL data (git-ignored, never committed).
    * ``seed.sample.json`` — anonymised demo data (committed).

On first run (empty DB) the loader prefers the local seed; the sample is only a
fallback for a fresh checkout. Amounts are human-readable German strings and
dates are TT.MM.JJJJ / MM.JJJJ, so the files stay easy to edit by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import sys

from app_meta import data_dir, is_frozen, resource_path
from modules import dates
from modules.db_handler.repositories import (
    CreditRepository,
    FixedCostRepository,
    IncomeRepository,
    VariableExpenseRepository,
)
from modules.logging_setup import get_logger
from modules.models import Credit, FixedCost, IncomeSource, VariableExpense
from modules.money import parse_eur

_log = get_logger("seed")


def _candidate_dirs() -> list[Path]:
    """Folders to search for seed files (user locations first)."""
    dirs = [data_dir(), data_dir() / "database"]
    # Next to the executable (lets a user drop in their real seed beside the app).
    # Only meaningful in a frozen build; in dev sys.executable is the interpreter.
    if is_frozen():
        exe_dir = Path(sys.executable).parent
        dirs += [exe_dir, exe_dir / "database"]
    # Bundled resources (the committed sample inside the build / dev tree).
    dirs.append(resource_path("database"))
    return dirs


def find_seed_file() -> Path | None:
    """Locate a seed file, preferring the real local one over the sample."""
    for name in ("seed.local.json", "seed.sample.json"):
        for folder in _candidate_dirs():
            candidate = folder / name
            if candidate.exists():
                return candidate
    return None


def database_is_empty(db) -> bool:
    row = db.query_one("SELECT COUNT(*) AS n FROM income_sources")
    fixed = db.query_one("SELECT COUNT(*) AS n FROM fixed_costs")
    return (row["n"] if row else 0) == 0 and (fixed["n"] if fixed else 0) == 0


def load_seed(db, path: Path) -> dict:
    """Load income, fixed costs, credits and estimate expenses from JSON.

    Returns a small summary dict for logging. Robust against missing keys.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    income_repo = IncomeRepository(db)
    fixed_repo = FixedCostRepository(db)
    credit_repo = CreditRepository(db)
    expense_repo = VariableExpenseRepository(db)

    counts = {"income": 0, "fixed": 0, "credits": 0, "expenses": 0}

    for row in data.get("income_sources", []):
        income_repo.add(IncomeSource(
            name=row["name"],
            amount_cents=parse_eur(row["amount"]),
            income_type=row.get("type", "sonstiges"),
            active=row.get("active", True),
            note=row.get("note", ""),
        ))
        counts["income"] += 1

    for row in data.get("fixed_costs", []):
        end = row.get("end")
        start = row.get("start")
        fixed_repo.add(FixedCost(
            name=row["name"],
            amount_cents=parse_eur(row["amount"]),
            category=row.get("category", "Sonstiges"),
            start_date=dates.to_iso(dates.parse_date(start)) if start else None,
            end_date=dates.to_iso(dates.parse_date(end)) if end else None,
            note=row.get("note", ""),
        ))
        counts["fixed"] += 1

    for row in data.get("credits", []):
        credit_repo.add(Credit(
            name=row["name"],
            total_cents=parse_eur(row["total"]) if row.get("total") else None,
            monthly_cents=parse_eur(row["monthly"]) if row.get("monthly") else None,
            end_date=dates.to_iso(dates.parse_date(row["end"])) if row.get("end") else None,
            term_months=row.get("term"),
            interest_rate=row.get("rate"),
            category=row.get("category", "Divers"),
            note=row.get("note", ""),
        ))
        counts["credits"] += 1

    # Variable estimates become example expenses dated on the 1st of this month,
    # so the dashboard is meaningful immediately. The user can edit or delete them.
    first_of_month = dates.today().replace(day=1)
    for row in data.get("variable_estimate", []):
        expense_repo.add(VariableExpense(
            date=dates.to_iso(first_of_month),
            amount_cents=parse_eur(row["amount"]),
            category=row.get("category", "Sonstiges"),
            description=row.get("name", "Schätzung"),
        ))
        counts["expenses"] += 1

    _log.info("Seed geladen aus %s: %s", path.name, counts)
    return counts


def seed_if_empty(db) -> bool:
    """Seed the database on first run if it is empty and a seed file exists."""
    if not database_is_empty(db):
        return False
    path = find_seed_file()
    if path is None:
        return False
    try:
        load_seed(db, path)
        return True
    except Exception as exc:  # noqa: BLE001 - seeding must never block startup
        _log.warning("Seed konnte nicht geladen werden: %s", exc)
        return False

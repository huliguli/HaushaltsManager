"""Seed loader: optionally populate an EMPTY database from the user's own data.

Auto-seeding is deliberate and only ever uses ``seed.local.json`` — the user's
real data, which they place next to the executable or in %APPDATA%. That file is
git-ignored and is NEVER bundled into the build, so a freshly downloaded app
starts EMPTY (and shows the quick-setup wizard) instead of with demo values.

``seed.sample.json`` (committed, anonymised) is ONLY a format reference for the
repository — it is never bundled and never auto-loaded into a shipped app.

Amounts are human-readable German strings and dates are TT.MM.JJJJ / MM.JJJJ,
so the file stays easy to edit by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import sys

from app_meta import data_dir, is_frozen, resource_path
from modules import dates
from modules.db_handler.database import _CATEGORY_MIGRATION_V2
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

# The ONLY filename that may auto-seed. The anonymised seed.sample.json is a
# repo reference and must never appear here, or shipped builds would self-fill.
_AUTO_SEED_FILENAMES = ("seed.local.json",)


def _candidate_dirs() -> list[Path]:
    """Folders to search for the user's seed file.

    A frozen build only looks at user-controlled locations (%APPDATA% and next
    to the executable) — never at bundled resources — so a fresh download cannot
    auto-fill itself. In a dev run the repository's ``database`` folder is also
    searched, which is the developer's convenience for local testing.
    """
    dirs = [data_dir(), data_dir() / "database"]
    if is_frozen():
        # User drops their real seed beside the .exe.
        exe_dir = Path(sys.executable).parent
        dirs += [exe_dir, exe_dir / "database"]
    else:
        # Development: the repo's database/ folder (may hold seed.local.json).
        dirs.append(resource_path("database"))
    return dirs


def find_seed_file() -> Path | None:
    """Locate the user's seed file (seed.local.json) if present, else None."""
    for name in _AUTO_SEED_FILENAMES:
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
    # Seeding runs after the DB migration, so map any legacy expense-category name
    # from an older seed file onto the current v2 taxonomy (defensive: a fresh
    # install must not end up with orphaned category names).
    first_of_month = dates.today().replace(day=1)
    for row in data.get("variable_estimate", []):
        raw_cat = row.get("category", "Sonstiges")
        category = _CATEGORY_MIGRATION_V2.get(raw_cat, raw_cat)
        expense_repo.add(VariableExpense(
            date=dates.to_iso(first_of_month),
            amount_cents=parse_eur(row["amount"]),
            category=category,
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

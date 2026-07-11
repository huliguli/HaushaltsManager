"""Tests for the Abo-Radar detection (modules.subscriptions)."""

from datetime import date

from modules import subscriptions
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    FixedCostRepository,
    SubscriptionIgnoreRepository,
    VariableExpenseRepository,
)
from modules.models import FixedCost, VariableExpense

TODAY = date(2026, 7, 15)


def _exp(iso: str, cents: int, desc: str, category: str = "Streaming & Abos"):
    return VariableExpense(date=iso, amount_cents=cents, category=category,
                           description=desc)


def test_detects_monthly_subscription():
    items = [_exp(f"2026-{m:02d}-05", 1_299, "NETFLIX") for m in (3, 4, 5, 6, 7)]
    found = subscriptions.detect(items, today=TODAY)
    assert len(found) == 1
    s = found[0]
    assert s.interval_months == 1 and s.amount_cents == 1_299
    assert s.occurrences == 5 and s.yearly_cents == 12 * 1_299
    assert s.monthly_cents == 1_299
    assert s.price_increase is None


def test_detects_quarterly_and_yearly():
    quarterly = [_exp(iso, 4_500, "Versicherung KFZ", "Versicherung")
                 for iso in ("2025-10-01", "2026-01-02", "2026-04-01", "2026-07-01")]
    yearly = [_exp(iso, 5_999, "Domain Hosting", "Finanzen & Gebühren")
              for iso in ("2024-07-10", "2025-07-09", "2026-07-11")]
    found = subscriptions.detect(quarterly + yearly, today=TODAY)
    by_pattern = {s.pattern: s for s in found}
    kfz = by_pattern["versicherung kfz"]
    assert kfz.interval_months == 3
    assert kfz.monthly_cents == 1_500 and kfz.yearly_cents == 18_000
    host = by_pattern["domain hosting"]
    assert host.interval_months == 12 and host.yearly_cents == 5_999


def test_irregular_shopping_is_not_a_subscription():
    # Same merchant, wildly varying gaps and amounts -> must stay quiet.
    items = [_exp("2026-06-01", 2_350, "AMAZON", "Shopping & Online"),
             _exp("2026-06-04", 899, "AMAZON", "Shopping & Online"),
             _exp("2026-06-28", 12_990, "AMAZON", "Shopping & Online"),
             _exp("2026-07-10", 4_500, "AMAZON", "Shopping & Online")]
    assert subscriptions.detect(items, today=TODAY) == []


def test_needs_at_least_three_occurrences():
    items = [_exp("2026-05-05", 999, "SPOTIFY"), _exp("2026-06-05", 999, "SPOTIFY")]
    assert subscriptions.detect(items, today=TODAY) == []


def test_price_increase_is_flagged_with_since_date():
    items = [_exp("2026-02-05", 999, "SPOTIFY"),
             _exp("2026-03-05", 999, "SPOTIFY"),
             _exp("2026-04-07", 999, "SPOTIFY"),
             _exp("2026-05-05", 1_199, "SPOTIFY"),
             _exp("2026-06-05", 1_199, "SPOTIFY"),
             _exp("2026-07-06", 1_199, "SPOTIFY")]
    found = subscriptions.detect(items, today=TODAY)
    assert len(found) == 1
    inc = found[0].price_increase
    assert inc is not None
    assert inc.old_cents == 999 and inc.new_cents == 1_199
    assert inc.since_iso == "2026-05-05"
    assert found[0].amount_cents == 1_199    # current price, not the old one


def test_tiny_wiggle_is_not_an_increase():
    items = [_exp("2026-04-05", 1_000, "STROM ABSCHLAG", "Energie & Nebenkosten"),
             _exp("2026-05-05", 1_000, "STROM ABSCHLAG", "Energie & Nebenkosten"),
             _exp("2026-06-05", 1_010, "STROM ABSCHLAG", "Energie & Nebenkosten"),
             _exp("2026-07-06", 1_010, "STROM ABSCHLAG", "Energie & Nebenkosten")]
    found = subscriptions.detect(items, today=TODAY)
    assert len(found) == 1 and found[0].price_increase is None


def test_ended_subscription_is_skipped():
    # Last booking almost a year ago -> not an action item any more.
    items = [_exp(f"2025-{m:02d}-05", 1_299, "ALTES ABO") for m in (4, 5, 6, 7, 8)]
    assert subscriptions.detect(items, today=TODAY) == []


def test_ignored_and_known_patterns_are_excluded():
    items = [_exp(f"2026-{m:02d}-05", 999, "SPOTIFY") for m in (4, 5, 6, 7)]
    assert subscriptions.detect(items, ignored={"spotify"}, today=TODAY) == []
    assert subscriptions.detect(items, known={"spotify"}, today=TODAY) == []


def test_known_patterns_from_fixed_costs_and_templates():
    fixed = [FixedCost("Netflix", 1_299, "Freizeit"),
             FixedCost("Alte Miete", 50_000, "Wohnen", active=False)]
    templates = [VariableExpense(date="2026-01-05", amount_cents=999,
                                 description="Spotify", recurring=True)]
    known = subscriptions.known_patterns(fixed, templates)
    assert "netflix" in known and "spotify" in known
    assert "alte miete" not in known          # inactive fixed costs stay out


def test_fixed_category_mapping():
    assert subscriptions.fixed_category_for("Telekommunikation") == "Kommunikation"
    assert subscriptions.fixed_category_for("Streaming & Abos") == "Freizeit"
    assert subscriptions.fixed_category_for("Versicherung") == "Versicherung"
    assert subscriptions.fixed_category_for("Lebensmittel") == "Sonstiges"


def test_scan_wires_repositories_together(tmp_path):
    db = Database(tmp_path / "test.db")
    expenses = VariableExpenseRepository(db)
    fixed = FixedCostRepository(db)
    ignores = SubscriptionIgnoreRepository(db)

    for m in (3, 4, 5, 6, 7):
        expenses.add(_exp(f"2026-{m:02d}-05", 1_299, "NETFLIX"))
        expenses.add(_exp(f"2026-{m:02d}-12", 999, "SPOTIFY"))
    # Already modelled as a recurring template -> must not be re-suggested.
    expenses.add(VariableExpense(date="2026-03-20", amount_cents=899,
                                 category="Streaming & Abos",
                                 description="Disney Plus", recurring=True))

    found = subscriptions.scan(expenses, fixed, ignores, today=TODAY)
    assert {s.pattern for s in found} == {"netflix", "spotify"}

    # Hiding one pattern removes exactly that suggestion.
    ignores.add("spotify")
    found = subscriptions.scan(expenses, fixed, ignores, today=TODAY)
    assert {s.pattern for s in found} == {"netflix"}

    # Adopting the other as an (active) fixed cost silences it too.
    fixed.add(FixedCost("NETFLIX", 1_299, "Freizeit"))
    assert subscriptions.scan(expenses, fixed, ignores, today=TODAY) == []
    db.close()


def test_results_sorted_by_yearly_cost():
    cheap = [_exp(f"2026-{m:02d}-05", 500, "GÜNSTIG") for m in (4, 5, 6, 7)]
    pricey = [_exp(f"2026-{m:02d}-10", 4_999, "TEUER") for m in (4, 5, 6, 7)]
    found = subscriptions.detect(cheap + pricey, today=TODAY)
    assert [s.pattern for s in found] == ["teuer", "gunstig"]

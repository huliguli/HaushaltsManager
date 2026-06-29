"""Tests for the fixed-cost reduction timeline (fictional sample data)."""

from datetime import date

from modules.calculator import timeline
from modules.models import FixedCost


def _costs():
    return [
        FixedCost("Miete", 50_000, "Wohnen", end_date=None),
        FixedCost("Ratenkredit", 8_000, "Kredit", end_date="2026-12-14"),
        FixedCost("Sparvertrag", 3_000, "Persönlich", end_date="2028-06-01"),
        FixedCost("Privatdarlehen", 2_000, "Persönlich", end_date="2028-08-01"),
    ]


def test_current_totals():
    res = timeline.build(300_000, _costs(), frm=date(2026, 6, 29))
    assert res.current_fixed_total_cents == 63_000
    assert res.current_available_cents == 300_000 - 63_000


def test_events_order_and_amounts():
    res = timeline.build(300_000, _costs(), frm=date(2026, 6, 29))
    assert len(res.events) == 3

    dec, jun, aug = res.events
    assert dec.label == "Dez. 2026"
    assert dec.dropped_amount_cents == 8_000
    assert dec.new_fixed_total_cents == 55_000
    assert dec.available_after_fixed_cents == 300_000 - 55_000

    assert jun.dropped_amount_cents == 3_000
    assert jun.new_fixed_total_cents == 52_000

    assert aug.dropped_amount_cents == 2_000
    assert aug.new_fixed_total_cents == 50_000  # only the open-ended rent remains


def test_past_costs_excluded():
    costs = [FixedCost("Alt", 5_000, "Sonstiges", end_date="2020-01-01")]
    res = timeline.build(100_000, costs, frm=date(2026, 6, 29))
    assert res.current_fixed_total_cents == 0
    assert res.events == []

"""Tests for German date parsing and month arithmetic."""

from datetime import date

from modules import dates


def test_parse_full_dates():
    assert dates.parse_date("14.12.2026") == date(2026, 12, 14)
    assert dates.parse_date("01.08.2028") == date(2028, 8, 1)
    assert dates.parse_date("2026-12-14") == date(2026, 12, 14)
    assert dates.parse_date("") is None
    assert dates.parse_date(None) is None


def test_parse_month_year():
    # "03.2032" -> last day of March 2032
    assert dates.parse_date("03.2032") == date(2032, 3, 31)
    assert dates.parse_date("01.2030") == date(2030, 1, 31)
    # The slashed form must resolve to the last day too (not the 1st).
    assert dates.parse_date("06/2026") == date(2026, 6, 30)


def test_format():
    assert dates.format_date(date(2026, 12, 14)) == "14.12.2026"
    assert dates.format_date("2028-08-01") == "01.08.2028"
    assert dates.format_date(None) == ""


def test_add_months():
    assert dates.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert dates.add_months(date(2026, 12, 15), 2) == date(2027, 2, 15)
    assert dates.add_months(date(2026, 6, 30), -6) == date(2025, 12, 30)


def test_months_between():
    assert dates.months_between(date(2026, 1, 1), date(2026, 4, 1)) == 3
    assert dates.months_between(date(2026, 1, 15), date(2026, 4, 1)) == 2
    assert dates.months_between(date(2026, 4, 1), date(2026, 1, 1)) == -3


def test_months_remaining():
    frm = date(2026, 6, 29)
    assert dates.months_remaining(None, frm) is None
    # December 2026 end -> exactly 6 months left (deterministic, not just > 0).
    assert dates.months_remaining("14.12.2026", frm) == 6
    # Past date -> exact overdue distance (deterministic, not just < 0).
    assert dates.months_remaining("01.01.2020", frm) == -78


def test_format_months_remaining():
    assert dates.format_months_remaining(None) == "unbegrenzt"
    assert dates.format_months_remaining(-1) == "überfällig"
    assert dates.format_months_remaining(1) == "noch 1 Monat"
    assert dates.format_months_remaining(5) == "noch 5 Monate"
    assert dates.format_months_remaining(24) == "noch 2 Jahre"

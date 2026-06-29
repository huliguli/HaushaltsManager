"""Tests for cent arithmetic and German money formatting/parsing."""

import pytest

from modules.money import (
    MoneyParseError,
    cents_to_euros,
    euros_to_cents,
    format_eur,
    format_eur_short,
    parse_eur,
)


def test_format_basic():
    assert format_eur(123456) == "1.234,56 €"
    assert format_eur(0) == "0,00 €"
    assert format_eur(5) == "0,05 €"
    assert format_eur(-50000) == "-500,00 €"
    assert format_eur(185000) == "1.850,00 €"
    assert format_eur(100000000) == "1.000.000,00 €"


def test_format_options():
    assert format_eur(123456, symbol=False) == "1.234,56"
    assert format_eur(75000, plus=True) == "+750,00 €"
    assert format_eur(-100, plus=True) == "-1,00 €"
    assert format_eur_short(123400) == "1.234 €"
    assert format_eur_short(123456) == "1.234,56 €"


def test_parse_german():
    assert parse_eur("1.234,56 €") == 123456
    assert parse_eur("1.234,56") == 123456
    assert parse_eur("500,00") == 50000
    assert parse_eur("1.500") == 150000        # German thousands, no decimals
    assert parse_eur("1.234.567") == 123456700  # multiple thousands groups
    assert parse_eur("10") == 1000


def test_parse_plain_and_us():
    assert parse_eur("1234.56") == 123456       # US/plain decimal
    assert parse_eur("1234,56") == 123456
    assert parse_eur("0.05") == 5
    assert parse_eur("100.00") == 10000
    assert parse_eur("1,234.56") == 123456      # US grouping + decimal


def test_parse_signs_and_symbols():
    assert parse_eur("-58,80") == -5880
    assert parse_eur("  12,00 EUR ") == 1200
    assert parse_eur(1850) == 185000
    assert parse_eur(1850.5) == 185050


def test_parse_errors():
    with pytest.raises(MoneyParseError):
        parse_eur("")
    with pytest.raises(MoneyParseError):
        parse_eur("abc")
    with pytest.raises(MoneyParseError):
        parse_eur(None)


def test_roundtrip():
    for cents in (0, 5, 100, 50000, 123456, 100000000, -5000):
        assert parse_eur(format_eur(cents, symbol=False)) == cents


def test_cent_conversions():
    assert euros_to_cents("12.5") == 1250
    assert euros_to_cents(0.1 + 0.2) == 30        # float noise rounded away
    assert cents_to_euros(12345) == 123.45

import datetime as dt

import pytest

from invoices.normalize import (
    edit_distance,
    is_absent,
    normalize_amount,
    normalize_currency,
    normalize_date,
    normalize_text,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2024-05-10", dt.date(2024, 5, 10)),
        ("10.05.2024", dt.date(2024, 5, 10)),
        ("10/05/2024", dt.date(2024, 5, 10)),
        ("10-05-2024", dt.date(2024, 5, 10)),
        ("10 травня 2024 року", dt.date(2024, 5, 10)),
        ("10 тра 2024", dt.date(2024, 5, 10)),
        ("10 ТРАВНЯ 2024 р.", dt.date(2024, 5, 10)),
        ("2024/05/10", dt.date(2024, 5, 10)),
        ("  10.05.2024.  ", dt.date(2024, 5, 10)),
        ("29.02.2024", dt.date(2024, 2, 29)),
        (dt.date(2024, 5, 10), dt.date(2024, 5, 10)),
    ],
)
def test_normalize_date(value, expected):
    assert normalize_date(value) == expected


@pytest.mark.parametrize(
    "value",
    ["31.02.2024", "10.13.2024", "10 травня 24", "10 мартобря 2024", "", "учора", None, 5]
)
def test_normalize_date_invalid(value):
    with pytest.raises(ValueError):
        normalize_date(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1234.56", 1234.56),
        ("1\u00a0234,56", 1234.56),
        ("1 234,56 грн", 1234.56),
        ("1,234.56", 1234.56),
        ("1.234,56", 1234.56),
        ("1234,56", 1234.56),
        ("₴ 1 234,56", 1234.56),
        ("1,234,567.89", 1234567.89),
        ("12 345", 12345.0),
        ("-12.50", -12.5),
        ("0", 0.0),
        (1234.56, 1234.56),
        (7, 7.0),
    ],
)
def test_normalize_amount(value, expected):
    assert normalize_amount(value) == pytest.approx(expected)


def test_single_comma_is_decimal_separator():
    # Правило задокументоване: одиночна кома завжди десяткова.
    assert normalize_amount("1,234") == pytest.approx(1.234)


@pytest.mark.parametrize("value", ["", "abc", "-", None, True, "12abc", float("inf")])
def test_normalize_amount_invalid(value):
    with pytest.raises(ValueError):
        normalize_amount(value)


@pytest.mark.parametrize(
    "value,expected",
    [("грн", "UAH"), ("₴", "UAH"), ("UAH", "UAH"), ("$", "USD"), ("usd", "USD"),
     ("€", "EUR"), ("zł", "PLN"), ("PLN.", "PLN")],
)
def test_normalize_currency(value, expected):
    assert normalize_currency(value) == expected


@pytest.mark.parametrize("value", ["", "гроші", None, 980])
def test_normalize_currency_invalid(value):
    with pytest.raises(ValueError):
        normalize_currency(value)


@pytest.mark.parametrize("value", [None, "", "  ", "Без ПДВ", "відсутній", "н/д", "N/A"])
def test_is_absent_true(value):
    assert is_absent(value) is True


@pytest.mark.parametrize("value", [0, "0", "200.00", "ПДВ є"])
def test_is_absent_false(value):
    assert is_absent(value) is False


def test_normalize_text_removes_quotes_and_case():
    assert normalize_text("ТОВ «Крига  Софт»") == normalize_text('тов "крига софт"')


@pytest.mark.parametrize(
    "a,b,limit,expected",
    [(" abc", "abc", 1, 1), ("abc", "abc", 0, 0), ("abc", "abd", 1, 1),
     ("abc", "abcd", 0, 1), ("abc", "xyz", 1, 2)],
)
def test_edit_distance(a, b, limit, expected):
    assert edit_distance(a, b, limit) == expected

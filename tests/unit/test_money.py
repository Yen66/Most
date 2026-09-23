from decimal import Decimal

import pytest

from construction_os.money import (
    add_vat,
    as_decimal,
    extract_vat,
    money,
    round_position,
    sum_positions,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", Decimal("1.00")),
        ("1.004", Decimal("1.00")),
        ("1.005", Decimal("1.01")),
        ("-1.005", Decimal("-1.01")),
        (2, Decimal("2.00")),
        (Decimal("3.456"), Decimal("3.46")),
    ],
)
def test_money_rounding(raw, expected):
    assert money(raw) == expected


def test_excel_float_normalized_without_binary_tail():
    assert as_decimal(42860.189999999995) == Decimal("42860.189999999995")
    assert money(42860.189999999995) == Decimal("42860.19")


def test_round_position():
    assert round_position(Decimal("2"), Decimal("42860.19")) == Decimal("85720.38")


def test_sum_positions():
    assert sum_positions([Decimal("1.11"), Decimal("2.22")]) == Decimal("3.33")


def test_extract_vat_reference():
    pair = extract_vat(Decimal("35656922.00"), Decimal("0.22"))
    assert pair.net == Decimal("29226985.25")
    assert pair.vat == Decimal("6429936.75")


def test_extract_vat_invariant():
    pair = extract_vat(Decimal("0.01"), Decimal("0.22"))
    assert pair.net + pair.vat == pair.gross


def test_add_vat_invariant():
    pair = add_vat(Decimal("100.00"), Decimal("0.22"))
    assert pair.gross == Decimal("122.00")
    assert pair.net + pair.vat == pair.gross

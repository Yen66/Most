from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def as_decimal(value: Decimal | int | str | float) -> Decimal:
    """Normalize an external scalar to Decimal without binary arithmetic."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def money(value: Decimal | int | str | float) -> Decimal:
    return as_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def from_excel_float(value: Decimal | int | str | float) -> Decimal:
    return money(value)


def round_position(
    quantity: Decimal | int | str | float,
    price_gross: Decimal | int | str | float,
) -> Decimal:
    return money(as_decimal(quantity) * money(price_gross))


def sum_positions(values: Iterable[Decimal | int | str | float]) -> Decimal:
    return money(sum((money(value) for value in values), Decimal("0")))


@dataclass(frozen=True, slots=True)
class VatPair:
    gross: Decimal
    net: Decimal
    vat: Decimal


def extract_vat(gross: Decimal | int | str | float, rate: Decimal) -> VatPair:
    gross_value = money(gross)
    net = money(gross_value / (Decimal("1") + rate))
    vat = money(gross_value - net)
    vat += gross_value - (net + vat)
    return VatPair(gross_value, net, vat)


def add_vat(net: Decimal | int | str | float, rate: Decimal) -> VatPair:
    net_value = money(net)
    gross = money(net_value * (Decimal("1") + rate))
    vat = money(gross - net_value)
    return VatPair(gross, net_value, vat)

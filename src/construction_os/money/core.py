from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

CENT = Decimal("0.01")

def as_decimal(value: Decimal | int | str | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value)) if isinstance(value, float) else Decimal(value)

def money(value: Decimal | int | str | float) -> Decimal:
    return as_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)

def from_excel_float(value: Decimal | int | str | float) -> Decimal:
    return money(value)

def round_position(quantity: Decimal | int | str | float, price_gross: Decimal | int | str | float) -> Decimal:
    price = money(price_gross)
    return money(as_decimal(quantity) * price)

def sum_positions(values: Iterable[Decimal | int | str | float]) -> Decimal:
    return money(sum((money(v) for v in values), Decimal("0")))

@dataclass(frozen=True, slots=True)
class VatPair:
    gross: Decimal
    net: Decimal
    vat: Decimal

def extract_vat(gross: Decimal | int | str | float, rate: Decimal) -> VatPair:
    gross_q = money(gross)
    net = money(gross_q / (Decimal("1") + rate))
    vat = money(gross_q - net)
    vat += gross_q - (net + vat)
    return VatPair(gross_q, net, vat)

def add_vat(net: Decimal | int | str | float, rate: Decimal) -> VatPair:
    net_q = money(net)
    gross = money(net_q * (Decimal("1") + rate))
    vat = money(gross - net_q)
    return VatPair(gross, net_q, vat)

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class RateType(StrEnum):
    VAT_RATE = "VAT_RATE"
    PROFIT_TAX = "PROFIT_TAX"
    KEY_RATE = "KEY_RATE"
    INSURANCE_PREMIUM = "INSURANCE_PREMIUM"
    WINTER_SURCHARGE = "WINTER_SURCHARGE"


class RateNotFoundError(LookupError):
    """Raised when a dated reference rate cannot be resolved uniquely."""


@dataclass(frozen=True, slots=True)
class ReferenceRate:
    rate_type: RateType
    value: Decimal
    valid_from: date
    valid_to: date | None = None
    document_number: str | None = None
    document_date: date | None = None

    def covers(self, on_date: date) -> bool:
        return self.valid_from <= on_date and (self.valid_to is None or on_date <= self.valid_to)


INITIAL_RATES = (
    ReferenceRate(
        RateType.VAT_RATE,
        Decimal("0.20"),
        date(2019, 1, 1),
        date(2025, 12, 31),
        "303-ФЗ",
        date(2018, 8, 3),
    ),
    ReferenceRate(
        RateType.VAT_RATE,
        Decimal("0.22"),
        date(2026, 1, 1),
        None,
        "425-ФЗ",
        date(2025, 11, 28),
    ),
    ReferenceRate(RateType.PROFIT_TAX, Decimal("0.25"), date(2025, 1, 1)),
    ReferenceRate(RateType.KEY_RATE, Decimal("0.14"), date(2026, 9, 18)),
)


def get_rate(
    rate_type: RateType | str,
    on_date: date,
    rates: Iterable[ReferenceRate] = INITIAL_RATES,
) -> ReferenceRate:
    kind = RateType(rate_type)
    found = [rate for rate in rates if rate.rate_type == kind and rate.covers(on_date)]
    if len(found) != 1:
        raise RateNotFoundError(f"{kind} coverage for {on_date}: {len(found)} rows")
    return found[0]

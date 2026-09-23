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
    # 11.09.2026: ставка 14% сохранена, нового периода нет.
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.21"), date(2024, 10, 28),
        date(2025, 6, 8),
        "пресс-релиз ЦБ РФ от 25.10.2024", date(2024, 10, 25),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.20"), date(2025, 6, 9),
        date(2025, 7, 27),
        "пресс-релиз ЦБ РФ от 06.06.2025", date(2025, 6, 6),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.18"), date(2025, 7, 28),
        date(2025, 9, 14),
        "пресс-релиз ЦБ РФ от 25.07.2025", date(2025, 7, 25),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.17"), date(2025, 9, 15),
        date(2025, 10, 26),
        "пресс-релиз ЦБ РФ от 12.09.2025", date(2025, 9, 12),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.165"), date(2025, 10, 27),
        date(2025, 12, 21),
        "пресс-релиз ЦБ РФ от 24.10.2025", date(2025, 10, 24),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.16"), date(2025, 12, 22),
        date(2026, 2, 15),
        "пресс-релиз ЦБ РФ от 19.12.2025", date(2025, 12, 19),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.155"), date(2026, 2, 16),
        date(2026, 3, 22),
        "пресс-релиз ЦБ РФ от 13.02.2026", date(2026, 2, 13),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.15"), date(2026, 3, 23),
        date(2026, 4, 26),
        "пресс-релиз ЦБ РФ от 20.03.2026", date(2026, 3, 20),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.145"), date(2026, 4, 27),
        date(2026, 6, 21),
        "пресс-релиз ЦБ РФ от 24.04.2026", date(2026, 4, 24),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.1425"), date(2026, 6, 22),
        date(2026, 7, 26),
        "пресс-релиз ЦБ РФ от 19.06.2026", date(2026, 6, 19),
    ),
    ReferenceRate(
        RateType.KEY_RATE, Decimal("0.14"), date(2026, 7, 27),
        None,
        "пресс-релиз ЦБ РФ от 24.07.2026", date(2026, 7, 24),
    ),
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

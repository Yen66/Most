from datetime import date
from decimal import Decimal

import pytest

from construction_os.references import RateNotFoundError, RateType, ReferenceRate, get_rate


def test_vat_2025():
    assert get_rate(RateType.VAT_RATE, date(2025, 9, 1)).value == Decimal("0.20")


def test_vat_2026():
    assert get_rate(RateType.VAT_RATE, date(2026, 9, 1)).value == Decimal("0.22")


def test_vat_boundary_2025():
    assert get_rate(RateType.VAT_RATE, date(2025, 12, 31)).value == Decimal("0.20")


def test_vat_boundary_2026():
    assert get_rate(RateType.VAT_RATE, date(2026, 1, 1)).value == Decimal("0.22")


def test_rate_missing():
    with pytest.raises(RateNotFoundError):
        get_rate(RateType.VAT_RATE, date(2010, 1, 1))


def test_rate_overlap_rejected():
    rates = [
        ReferenceRate(RateType.VAT_RATE, Decimal("0.20"), date(2020, 1, 1)),
        ReferenceRate(RateType.VAT_RATE, Decimal("0.22"), date(2020, 1, 1)),
    ]
    with pytest.raises(RateNotFoundError):
        get_rate(RateType.VAT_RATE, date(2026, 1, 1), rates)

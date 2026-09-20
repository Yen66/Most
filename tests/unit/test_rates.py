from datetime import date
from decimal import Decimal
import pytest
from construction_os.references import RateNotFoundError, RateType, get_rate

def test_vat_2026():
    assert get_rate(RateType.VAT_RATE,date(2026,9,1)).value==Decimal("0.22")
def test_vat_2025():
    assert get_rate(RateType.VAT_RATE,date(2025,9,1)).value==Decimal("0.20")
def test_outside_coverage_raises():
    with pytest.raises(RateNotFoundError):
        get_rate(RateType.VAT_RATE,date(2018,12,31))

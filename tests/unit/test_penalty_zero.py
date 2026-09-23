from datetime import date
from decimal import Decimal

from construction_os.calc.penalty import calculate_penalty


def test_no_delay_before_key_rate_catalog_coverage():
    result = calculate_penalty(
        Decimal("1000000"),
        date(2024, 10, 1),
        as_of=date(2024, 10, 5),
        paid_on=date(2024, 10, 1),
        paid_amount=Decimal("1000000"),
    )
    assert result.total == Decimal("0.00")
    assert result.days == 0
    assert result.rate_history == ()
    assert result.segments == ()


def test_no_delay_ignores_explicit_uncovered_rate_date():
    result = calculate_penalty(
        Decimal("1000000"),
        date(2024, 10, 1),
        as_of=date(2024, 10, 5),
        paid_on=date(2024, 10, 1),
        paid_amount=Decimal("1000000"),
        rate_date=date(2024, 9, 1),
        penalty_cap_pct=Decimal("0.05"),
    )
    assert result.total == Decimal("0.00")
    assert result.cap_value == Decimal("50000.00")
    assert result.rate_history == ()

from datetime import date
from decimal import Decimal

from construction_os.calc import calculate_portfolio, calculate_revenue_for_date


def test_real_reference_total():
    result = calculate_revenue_for_date(Decimal("35656922.00"), date(2026, 9, 20))
    assert result.net == Decimal("29226985.25")
    assert result.vat == Decimal("6429936.75")


def test_portfolio_reference():
    result = calculate_portfolio(
        [Decimal("35656922.00"), Decimal("115397900.00"), Decimal("47635990.22")],
        date(2026, 9, 20),
    )
    assert result.gross == Decimal("198690812.22")
    assert result.net == Decimal("162861321.49")

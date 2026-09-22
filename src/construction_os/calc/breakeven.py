from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from construction_os.money import add_vat, money


@dataclass(frozen=True, slots=True)
class ThresholdResult:
    value: Decimal | None
    reason: str | None = None


def breakeven_net(
    costs_production: Decimal, financial_fixed: Decimal, financial_share: Decimal
) -> ThresholdResult:
    denominator = Decimal("1") - financial_share
    if denominator <= 0:
        return ThresholdResult(None, "доля финансовых расходов делает знаменатель неположительным")
    return ThresholdResult(money((costs_production + financial_fixed) / denominator))


def max_price_reduction(revenue_net: Decimal, breakeven: Decimal | None) -> ThresholdResult:
    if revenue_net <= 0:
        return ThresholdResult(None, "выручка без НДС должна быть больше нуля")
    if breakeven is None:
        return ThresholdResult(None, "точка безубыточности не определена")
    return ThresholdResult(money((Decimal("1") - breakeven / revenue_net) * Decimal("100")))


def min_revenue_for_margin(
    costs_production: Decimal, financial_fixed: Decimal, financial_share: Decimal, margin: Decimal
) -> ThresholdResult:
    denominator = Decimal("1") - margin - financial_share
    if denominator <= 0:
        return ThresholdResult(
            None, "целевая маржа и финансовая доля делают знаменатель неположительным"
        )
    return ThresholdResult(money((costs_production + financial_fixed) / denominator))


def gross_from_net(net: Decimal, vat_rate: Decimal) -> Decimal:
    return add_vat(money(net), vat_rate).gross

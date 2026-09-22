from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from construction_os.money import money

@dataclass(frozen=True, slots=True)
class ProfitResult:
    revenue_net: Decimal
    costs_production: Decimal
    financial_fixed: Decimal
    financial_share: Decimal
    financial_costs: Decimal
    total_costs: Decimal
    profit_before_tax: Decimal
    income_tax: Decimal
    net_profit: Decimal
    margin_pct: Decimal | None

def calculate_profit(revenue_net: Decimal, costs_production: Decimal, financial_fixed: Decimal, financial_share: Decimal, profit_tax_rate: Decimal) -> ProfitResult:
    financial=financial_fixed+revenue_net*financial_share
    total=costs_production+financial
    profit=revenue_net-total
    rounded_profit=money(profit)
    tax=money(rounded_profit*profit_tax_rate) if rounded_profit>0 else Decimal("0.00")
    net_profit=money(rounded_profit-tax)
    margin=money(profit/revenue_net*Decimal("100")) if revenue_net>0 else None
    return ProfitResult(money(revenue_net),money(costs_production),money(financial_fixed),financial_share,money(financial),money(total),rounded_profit,tax,net_profit,margin)

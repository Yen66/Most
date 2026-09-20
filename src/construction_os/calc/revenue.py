from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from construction_os.money import extract_vat,sum_positions
from construction_os.references import RateType,get_rate

@dataclass(frozen=True,slots=True)
class RevenueResult:
    gross:Decimal; net:Decimal; vat:Decimal; vat_rate:Decimal

def calculate_revenue_for_date(gross:Decimal,on_date:date)->RevenueResult:
    rate=get_rate(RateType.VAT_RATE,on_date).value;pair=extract_vat(gross,rate)
    return RevenueResult(pair.gross,pair.net,pair.vat,rate)

def calculate_portfolio(values:list[Decimal],on_date:date)->RevenueResult:
    return calculate_revenue_for_date(sum_positions(values),on_date)

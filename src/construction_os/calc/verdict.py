from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from construction_os.money import extract_vat, money

D = Decimal
BID_REDUCTIONS = (D("0"), D("0.05"), D("0.08"), D("0.10"), D("0.15"), D("0.20"), D("0.22"))
RISK_CODES = ("WINTER", "TEMP_FAC", "TRAFFIC", "MOB", "DRAIN", "LAB_CONTROL")
RISK_REFERENCES = {
    "WINTER": "приказ Минстроя 325/пр от 25.05.2021",
    "TEMP_FAC": "временные здания и сооружения: проверить сметные нормативы",
    "TRAFFIC": "проект ОДД: проверить условия производства работ",
    "MOB": "мобилизация/перебазировка: проверить организацию строительства",
    "DRAIN": "водоотлив: проверить проектные условия",
    "LAB_CONTROL": "лабораторный контроль: проверить проект и программу контроля",
}
ENTER_MARGIN_PCT = D("10")
CAUTION_MARGIN_PCT = D("3")


@dataclass(frozen=True, slots=True)
class BidRow:
    reduction: Decimal
    gross: Decimal
    net: Decimal
    vat: Decimal
    delta_net: Decimal
    is_award: bool = False


@dataclass(frozen=True, slots=True)
class Completeness:
    risks: tuple[str, ...]
    missing_other: tuple[str, ...]
    present_count: int
    total_count: int


def bid_grid(
    amounts_gross: list[Decimal] | tuple[Decimal, ...],
    vat_rate: Decimal,
    award_factor: Decimal | None = None,
) -> tuple[BidRow, ...]:
    """Round EACH work position before summation; extract VAT once per object."""
    if award_factor is not None and not (D("0") < award_factor <= D("1")):
        raise ValueError("award_reduction_factor must be within (0, 1]")
    if not amounts_gross:
        raise ValueError("нет данных: позиции ВОР")
    base_gross = money(sum((money(amount) for amount in amounts_gross), D("0")))
    base_net = extract_vat(base_gross, vat_rate).net

    def row(reduction: Decimal, award: bool = False) -> BidRow:
        gross = money(
            sum((money(amount * (D("1") - reduction)) for amount in amounts_gross), D("0"))
        )
        pair = extract_vat(gross, vat_rate)
        return BidRow(reduction, pair.gross, pair.net, pair.vat, money(pair.net - base_net), award)

    result = [row(reduction) for reduction in BID_REDUCTIONS]
    if award_factor is not None:
        result.append(row(D("1") - award_factor, True))
    return tuple(result)


def cost_completeness(
    present_codes: set[str], all_codes: list[str] | tuple[str, ...]
) -> Completeness:
    catalog = set(all_codes)
    absent = catalog - present_codes
    risks = tuple(code for code in RISK_CODES if code in absent)
    others = tuple(code for code in all_codes if code in absent and code not in RISK_CODES)
    return Completeness(risks, others, len(catalog & present_codes), len(catalog))


def traffic_light(profit_before_tax: Decimal | None, revenue_net: Decimal) -> str | None:
    if profit_before_tax is None or revenue_net <= 0:
        return None
    if profit_before_tax <= 0:
        return "НЕ ВХОДИТЬ"
    margin = profit_before_tax / revenue_net * D("100")
    if margin >= ENTER_MARGIN_PCT:
        return "ВХОДИТЬ"
    if margin >= CAUTION_MARGIN_PCT:
        return "ОСТОРОЖНО — запас тонкий"
    return "НЕ ВХОДИТЬ"


def vat_warnings(file_rates: set[Decimal], reference_rate: Decimal, on_date) -> tuple[str, ...]:
    return tuple(
        f"в файле ставка {(rate * D('100')).normalize():f}% — действующая ставка на {on_date}: "
        f"{(reference_rate * D('100')).normalize():f}% (425-ФЗ с 01.01.2026); "
        "файл создан до 2026 или ставка ошибочна"
        for rate in sorted(file_rates)
        if rate != reference_rate
    )

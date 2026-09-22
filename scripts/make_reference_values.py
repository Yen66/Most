from __future__ import annotations

from datetime import date
from decimal import Decimal

from construction_os.calc import (
    breakeven_net,
    calculate_profit,
    gross_from_net,
    max_price_reduction,
    min_revenue_for_margin,
)
from construction_os.references import RateType, get_rate

D = Decimal
ON_DATE = date(2026, 9, 20)


def m(v):
    return f"{v:,.2f}".replace(",", " ")


def p(v):
    return f"{v:.2f}%"


def case(title, production, fixed, share, revenue=None):
    revenue = revenue or D("1000000")
    tax = get_rate(RateType.PROFIT_TAX, ON_DATE).value
    vat = get_rate(RateType.VAT_RATE, ON_DATE).value
    result = calculate_profit(revenue, production, fixed, share, tax)
    be = breakeven_net(production, fixed, share)
    red = max_price_reduction(revenue, be.value)
    lines = [
        f"## {title}",
        "",
        "| Показатель | Значение |",
        "|---|---:|",
        f"| Выручка без НДС | {m(result.revenue_net)} |",
        f"| Производственные затраты | {m(result.costs_production)} |",
        f"| Финансовые фиксированные | {m(result.financial_fixed)} |",
        f"| Финансовая доля | {p(share * D('100'))} |",
        f"| Прибыль до налога | {m(result.profit_before_tax)} |",
        f"| Налог | {m(result.income_tax)} |",
        f"| Чистая прибыль | {m(result.net_profit)} |",
        f"| Маржа | {p(result.margin_pct)} |",
        f"| Точка безубыточности | {m(be.value)} |",
        f"| Максимальное снижение | {p(red.value)} |",
        "",
        "### Минимальная выручка",
        "",
        "| Маржа | Без НДС | С НДС |",
        "|---:|---:|---:|",
    ]
    for margin in (D("0"), D("0.05"), D("0.08"), D("0.10")):
        x = min_revenue_for_margin(production, fixed, share, margin).value
        lines.append(f"| {p(margin * D('100'))} | {m(x)} | {m(gross_from_net(x, vat))} |")
    return lines


def render():
    lines = [
        "# Эталонные значения расчётного ядра",
        "",
        *case("Кейс 1 — фиксированные финансовые", D("870000"), D("27000"), D("0")),
        "",
        *case("Кейс 2 — финансовая доля", D("870000"), D("0"), D("0.027")),
        "",
    ]
    tax = get_rate(RateType.PROFIT_TAX, ON_DATE).value
    c3 = calculate_profit(D("1000000"), D("882345.67"), D("27000"), D("0"), tax)
    lines += [
        "## Кейс 3 — other не теряется",
        "",
        f"Производственные: {m(c3.costs_production)}; итого: {m(c3.total_costs)}; прибыль: {m(c3.profit_before_tax)}; налог: {m(c3.income_tax)}; чистая прибыль: {m(c3.net_profit)}; маржа: {p(c3.margin_pct)}.",
        "",
        "## Сценарии кейса 1",
        "",
        "- MAT +10%: прибыль до налога 53 000.00",
        "- Все производственные +10%: прибыль до налога 16 000.00",
        "- Цена −8% и все производственные +10%: прибыль до налога −64 000.00",
        "- Зимнее удорожание 3%: 26 100.00; прибыль до налога 76 900.00",
        "",
        "## Чувствительность кейса 1",
        "",
        "| Снижение | Выручка | Итого затрат | Прибыль |",
        "|---:|---:|---:|---:|",
    ]
    for reduction in (D("0"), D("0.05"), D("0.10"), D("0.103"), D("0.11"), D("0.20")):
        r = D("1000000") * (D("1") - reduction)
        x = calculate_profit(r, D("870000"), D("27000"), D("0"), tax)
        lines.append(
            f"| {p(reduction * D('100'))} | {m(x.revenue_net)} | {m(x.total_costs)} | {m(x.profit_before_tax)} |"
        )
    lines += [
        "",
        "## Чувствительность кейса 2",
        "",
        "| Снижение | Выручка | Финансовые | Итого затрат | Прибыль |",
        "|---:|---:|---:|---:|---:|",
    ]
    for reduction in (D("0.05"), D("0.10"), D("0.10585817"), D("0.11")):
        r = D("1000000") * (D("1") - reduction)
        x = calculate_profit(r, D("870000"), D("0"), D("0.027"), tax)
        lines.append(
            f"| {p(reduction * D('100'))} | {m(x.revenue_net)} | {m(x.financial_costs)} | {m(x.total_costs)} | {m(x.profit_before_tax)} |"
        )
    return "\n".join(lines) + "\n"


def main():
    print(render(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

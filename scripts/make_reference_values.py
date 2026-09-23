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
from construction_os.calc.acts import payment_deadline, signing_deadline
from construction_os.calc.penalty import calculate_penalty
from construction_os.domain.calendar import CalendarNotCoveredError, add_working_days
from construction_os.references import RateType, get_rate
from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.references.rates import RateNotFoundError

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


def render_new_sections():
    """All values below are calculated by production functions, not copied formulas."""
    days = [*iter_calendar_days(2026), *iter_calendar_days(2027)]
    by_date = {row["cal_date"]: row for row in days}

    def working(day):
        if day not in by_date:
            raise CalendarNotCoveredError(f"calendar has no data for {day}")
        return by_date[day]["is_working"]

    lines = ["", "## Календарь", ""]
    for year in (2026, 2027):
        rows = [row for row in days if row["cal_date"].year == year]
        monthly = [
            sum(row["is_working"] for row in rows if row["cal_date"].month == month)
            for month in range(1, 13)
        ]
        lines.append(
            f"{year}: месяцы [{', '.join(map(str, monthly))}]; "
            f"рабочих {sum(row['is_working'] for row in rows)}; "
            f"нерабочих {sum(not row['is_working'] for row in rows)}."
        )
    lines += ["", "| Кейс | Начало | Рабочих дней | Результат |", "|---|---|---:|---|"]
    cases = (
        ("CAL-A", date(2026, 9, 1), 20),
        ("CAL-B", date(2026, 9, 29), 7),
        ("CAL-C", date(2026, 9, 29), 10),
        ("CAL-D", date(2026, 12, 30), 3),
        ("CAL-E", date(2027, 2, 19), 1),
        ("CAL-F", date(2026, 9, 25), 20),
    )
    for name, start, n in cases:
        lines.append(f"| {name} | {start} | {n} | {add_working_days(start, n, working)} |")
    lines += ["", "## Ключевая ставка", "", "| Дата | Ставка |", "|---|---:|"]
    boundaries = (
        date(2024, 10, 27),
        date(2024, 10, 28),
        date(2025, 12, 31),
        date(2026, 2, 15),
        date(2026, 2, 16),
        date(2026, 3, 22),
        date(2026, 3, 23),
        date(2026, 4, 26),
        date(2026, 4, 27),
        date(2026, 6, 21),
        date(2026, 6, 22),
        date(2026, 7, 26),
        date(2026, 7, 27),
        date(2026, 8, 1),
        date(2026, 9, 23),
    )
    for day in boundaries:
        try:
            value = p(get_rate(RateType.KEY_RATE, day).value * D("100"))
        except RateNotFoundError:
            value = "нет данных"
        lines.append(f"| {day} | {value} |")
    lines += ["", "## Неустойка", "", "| Кейс | Сроки и сегменты | Пеня |", "|---|---|---:|"]
    amount = D("1000000")
    signed = signing_deadline(date(2026, 9, 1), working)
    due_eis = payment_deadline(signed, 7, working)
    due_treasury = payment_deadline(signed, 10, working)
    p1 = calculate_penalty(amount, due_eis, as_of=date(2026, 10, 28))
    p2 = calculate_penalty(amount, due_treasury, as_of=date(2026, 10, 28))
    p3 = calculate_penalty(
        amount,
        date(2026, 6, 15),
        paid_on=date(2026, 8, 15),
        paid_amount=amount,
        as_of=date(2026, 8, 20),
    )
    p4 = calculate_penalty(
        amount,
        date(2026, 1, 5),
        as_of=date(2026, 7, 24),
        penalty_cap_pct=D("0.05"),
    )
    p5 = calculate_penalty(
        amount,
        date(2026, 9, 10),
        paid_on=date(2026, 9, 30),
        paid_amount=D("400000"),
        as_of=date(2026, 10, 20),
    )
    p6 = calculate_penalty(
        amount,
        date(2026, 9, 10),
        paid_on=date(2026, 9, 10),
        paid_amount=amount,
        as_of=date(2026, 9, 20),
    )
    p7a = calculate_penalty(
        D("7300000"),
        date(2026, 9, 10),
        as_of=date(2026, 9, 20),
    )
    p7b = calculate_penalty(
        D("7300000"),
        date(2026, 9, 10),
        as_of=date(2026, 9, 30),
    )
    lines += [
        f"| P1 | подписан {signed}; due {due_eis}; {p1.days} дн.; "
        f"{p(p1.rate_used * D('100'))} | {m(p1.total)} |",
        f"| P2 | due {due_treasury}; {p2.days} дн.; {p(p2.rate_used * D('100'))} | {m(p2.total)} |",
        f"| P3 | {p3.days} дн.; ставка на дату оплаты "
        f"{p(p3.rate_used * D('100'))} | {m(p3.total)} |",
        f"| P4 | {p4.days} дн.; без потолка {m(p4.total_uncapped)}; "
        f"потолок {m(p4.cap_value)}; день {p4.cap_reached_day} | {m(p4.total)} |",
        f"| P5 | A: {p5.segments[0].days} дн., {m(p5.segments[0].amount)}; "
        f"B: {p5.segments[1].days} дн., {m(p5.segments[1].amount)} | {m(p5.total)} |",
        f"| P6 | {p6.days} дн. | {m(p6.total)} |",
        f"| P7 (10 дн.) | {p7a.days} дн. | {m(p7a.total)} |",
        f"| P7 (20 дн.) | {p7b.days} дн. | {m(p7b.total)} |",
        f"| P8 | повторно размещён 2026-09-25; новый срок "
        f"{signing_deadline(date(2026, 9, 25), working)} | — |",
    ]
    return "\n".join(lines) + "\n" + render_task13_sections() + render_verdict_sections()


def render_task13_sections():
    """CF1-CF5 and S1-S13/F6: derive every result from production modules."""
    from construction_os.calc.cashflow import Flow, daily_balances, financing_cost, gap_report
    from construction_os.calc.costs import CostArticle, CostEntry
    from construction_os.calc.scenarios import ScenarioParam
    from construction_os.calc.whatif import evaluate, goal_seek, sensitivity
    from construction_os.references.cost_articles import DEFAULT_COST_ARTICLES

    T = date.fromisoformat
    base_flows = [
        Flow(T("2026-09-15"), "outflow", D("600000"), "MAT"),
        Flow(T("2026-09-30"), "outflow", D("200000"), "LAB"),
        Flow(T("2026-10-08"), "inflow", D("1000000"), "act_payment"),
    ]
    cash_cases = (
        ("CF1", base_flows, T("2026-09-15"), T("2026-10-31")),
        (
            "CF2",
            [Flow(T("2026-09-01"), "inflow", D("300000"), "advance"), *base_flows],
            T("2026-09-01"),
            T("2026-10-31"),
        ),
        (
            "CF3",
            [
                Flow(T("2026-09-20"), "outflow", D("960000"), "SUB"),
                Flow(T("2026-10-08"), "inflow", D("950000"), "act_payment"),
            ],
            T("2026-09-20"),
            T("2026-10-31"),
        ),
        (
            "CF4",
            [
                Flow(T("2026-10-01"), "outflow", D("800000"), "MAT"),
                Flow(T("2026-10-20"), "inflow", D("1000000"), "act_payment", "fact"),
            ],
            T("2026-10-01"),
            T("2026-10-31"),
        ),
        (
            "CF5",
            [
                Flow(T("2026-09-01"), "inflow", D("500000"), "advance"),
                Flow(T("2026-09-20"), "outflow", D("400000"), "MAT"),
            ],
            T("2026-09-01"),
            T("2026-09-30"),
        ),
    )
    lines = [
        "",
        "## Cash-flow",
        "",
        "| Кейс | Дней в минусе | Максимум | Первая дата максимума | "
        "Первый минус | Выход | Финансирование | Баланс |",
        "|---|---:|---:|---|---|---|---:|---:|",
    ]
    for name, flows, start, end in cash_cases:
        balances = daily_balances(flows, start, end)
        gap = gap_report(balances)
        cost = financing_cost(balances, D("0.14"))
        lines.append(
            f"| {name} | {gap.deficit_days} | {m(gap.max_deficit)} | "
            f"{gap.max_deficit_date or 'нет'} | {gap.first_negative_date or 'нет'} | "
            f"{gap.recovered_date or 'нет'} | {m(cost)} | {m(balances[-1].balance)} |"
        )
    lines += [
        "",
        "CF3: удержание " + m(D("1000000") - D("950000")) + " — дата возврата неизвестна.",
        "",
        "## What-if",
        "",
        "| Кейс | Выручка | Производственные | Прибыль | Налог | Чистая | Маржа |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    articles = {
        code: CostArticle(code, cat, name, i)
        for i, (code, cat, name) in enumerate(DEFAULT_COST_ARTICLES, 1)
    }
    entries = [
        CostEntry(code, D(amount), vat_mode="net")
        for code, amount in (
            ("MAT", "500000"),
            ("LAB", "250000"),
            ("MACH_OWN", "70000"),
            ("OVR_SITE", "50000"),
            ("BANK_GUAR", "27000"),
        )
    ]
    P = ScenarioParam
    cases = (
        ("S1", []),
        ("S2", [P("cost_multiplier", D("1.10"), "cost_item", "MAT")]),
        ("S3", [P("price_reduction", D("0.08"))]),
        ("S4", [P("price_reduction", D("0.08")), P("cost_multiplier", D("1.10"))]),
        ("S5", [P("cost_multiplier", D("1.10"))]),
        (
            "S6",
            [P("price_reduction", D("0.08")), P("cost_multiplier", D("1.10"), "cost_item", "MAT")],
        ),
        ("S7", [P("financial_share_override", D("0.027"))]),
        ("S8", [P("cost_multiplier", D("1.10"), "category", "direct")]),
        ("S9", [P("cost_multiplier", D("1.05"), "cost_item", "MAT")]),
    )
    tax = get_rate(RateType.PROFIT_TAX, ON_DATE).value
    for name, params in cases:
        result = evaluate(entries, articles, D("1000000"), tax, params, D("0.22"))
        profit = result.profit
        lines.append(
            f"| {name} | {m(profit.revenue_net)} | {m(profit.costs_production)} | "
            f"{m(profit.profit_before_tax)} | {m(profit.income_tax)} | "
            f"{m(profit.net_profit)} | {p(profit.margin_pct)} |"
        )
    lines += [
        "",
        "## Goal-seek",
        "",
        "| Кейс | Цель | Прибыль-цель | m* | Проверочная прибыль | Остаток |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, target, profit in (
        ("S10", "item:MAT", D("0")),
        ("S11", "price", D("0")),
        ("S12", "all", D("0")),
        ("S13", "item:MAT", D("50000")),
    ):
        result = goal_seek(entries, articles, D("1000000"), tax, target, profit, vat_rate=D("0.22"))
        lines.append(
            f"| {name} | {target} | {m(profit)} | {result.multiplier:.6f} | "
            f"{m(result.checked_profit)} | {m(result.residual)} |"
        )
    lines += [
        "",
        "## Sensitivity",
        "",
        "| Параметр | Прибыль −step | Прибыль +step | Δ | Ранг |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in sensitivity(entries, articles, D("1000000"), tax, D("0.10"), D("0.22")):
        lines.append(
            f"| {row.parameter} | {m(row.minus_profit)} | {m(row.plus_profit)} | "
            f"{m(row.delta)} | {row.rank if row.rank is not None else '—'} |"
        )
    return "\n".join(lines) + "\n"



def render_verdict_sections():
    """E-V1/E-V2/E-V3/E-V5: derive values from the fixture and production functions."""
    import json
    from pathlib import Path

    from construction_os.calc.verdict import bid_grid, cost_completeness, traffic_light
    from construction_os.money import money
    from construction_os.references.cost_articles import DEFAULT_COST_ARTICLES

    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/data/vor_object_a.json"
    rows = json.loads(fixture.read_text(encoding="utf-8"))["items"]
    amounts = [money(D(str(row[3])) * money(D(str(row[4])))) for row in rows]
    vat = get_rate(RateType.VAT_RATE, ON_DATE).value
    bids = bid_grid(amounts, vat)
    complete = cost_completeness(set(), [code for code, _, _ in DEFAULT_COST_ARTICLES])
    tax = get_rate(RateType.PROFIT_TAX, ON_DATE).value
    demo = calculate_profit(D("1000000"), D("870000"), D("27000"), D("0"), tax)
    award = bid_grid([D("1220000")], vat, D("0.87"))[-1]
    award_profit = calculate_profit(award.net, D("870000"), D("27000"), D("0"), tax)
    lines = [
        "",
        "## Вердикт",
        "",
        f"Сетка E-V1 для объекта A: {len(rows)} позиций; позиционное округление, затем объектный сплит НДС 22%.",
        "",
        "| Снижение | С НДС | Без НДС | НДС | Δ без НДС |",
        "|---:|---:|---:|---:|---:|",
    ]
    for bid in bids:
        lines.append(
            f"| {p(bid.reduction * D('100'))} | {m(bid.gross)} | {m(bid.net)} | "
            f"{m(bid.vat)} | {m(bid.delta_net)} |"
        )
    lines += [
        "",
        "Полнота E-V2: нормативные риски "
        + ", ".join(complete.risks)
        + f" ({len(complete.risks)}); остальные отсутствующие статьи "
        + f"{len(complete.missing_other)}; всего отсутствует "
        + f"{len(complete.risks) + len(complete.missing_other)}.",
        "",
        f"Демо E-V3: прибыль до налога {m(demo.profit_before_tax)}; "
        f"маржа {p(demo.margin_pct)}; "
        f"светофор {traffic_light(demo.profit_before_tax, demo.revenue_net)}.",
        "",
        f"Демо E-V5 при факторе 0.87: снижение {p(award.reduction * D('100'))}; "
        f"с НДС {m(award.gross)}; без НДС {m(award.net)}; "
        f"прибыль {m(award_profit.profit_before_tax)}; "
        f"маржа {p(award_profit.margin_pct)}; "
        f"светофор {traffic_light(award_profit.profit_before_tax, award.net)}.",
        "",
    ]
    return "\n".join(lines)

def main():
    print(render() + render_new_sections(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

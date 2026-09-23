from __future__ import annotations

from datetime import date
from decimal import Decimal

from construction_os.calc.verdict import RISK_REFERENCES
from construction_os.reports import format_money_ru, format_percent
from construction_os.storage.verdict import load_verdict


def configure_verdict(sub) -> None:
    parser = sub.add_parser("verdict", help="оценка объекта без записи в БД")
    parser.add_argument("--company", required=True)
    parser.add_argument("--object", required=True)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())


def run_verdict(args, session) -> int:
    try:
        verdict = load_verdict(session, args.company, args.object, args.date)
    except LookupError as error:
        print(str(error))
        return 2
    report = verdict.report
    completeness = verdict.completeness
    print(
        f"{report.company.name} / {report.object_row.name} / {args.date} / "
        f"полнота {completeness.present_count}/{completeness.total_count}"
    )
    print(
        f"Выручка с НДС: {format_money_ru(report.revenue_gross)}; "
        f"без НДС: {format_money_ru(report.revenue_net)}; "
        f"НДС: {format_money_ru(report.vat)}; позиций: {verdict.positions}"
    )
    contract = report.contract
    if contract is None:
        print("Договор: нет данных")
    else:
        factor = contract.award_reduction_factor
        print(
            f"Договор: {contract.number or 'нет данных'}; "
            f"price_is_final={contract.price_is_final}; "
            f"award_reduction_factor={factor if factor is not None else 'нет данных'}"
        )
        print(
            f"Аванс: {contract.advance_pct if contract.advance_pct is not None else 'нет данных'}; "
            f"удержание: {contract.warranty_retention_pct if contract.warranty_retention_pct is not None else 'нет данных'}; "
            f"казначейство: {contract.treasury_account if contract.treasury_account is not None else 'нет данных'}"
        )
    for warning in verdict.warnings:
        print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
    print("Снижение | С НДС | Без НДС | НДС | Δ без НДС")
    for row in verdict.bids:
        label = (
            f"ваше снижение {format_percent(row.reduction * Decimal('100'))}"
            if row.is_award
            else format_percent(row.reduction * Decimal("100"))
        )
        print(
            f"{label} | {format_money_ru(row.gross)} | {format_money_ru(row.net)} | "
            f"{format_money_ru(row.vat)} | {format_money_ru(row.delta_net)}"
        )
    print("Нормативно вычисляемые риски — нет данных:")
    for code in completeness.risks:
        print(
            f"  {code} {verdict.article_names.get(code, code)} — нет данных; "
            f"обычно присутствует на объектах этого типа; {RISK_REFERENCES[code]}"
        )
    print("Остальные отсутствующие статьи — нет данных: " + ", ".join(completeness.missing_other))
    summary_status = verdict.status or "вердикт неполный — нет затрат"
    if verdict.status is None:
        print("вердикт неполный: нет данных по затратам — заполните costs template и costs import")
    else:
        profit = report.profit
        print(
            f"Прибыль до налога: {format_money_ru(profit.profit_before_tax)}; "
            f"налог: {format_money_ru(profit.income_tax)}; "
            f"маржа: {format_percent(profit.margin_pct)}; "
            f"светофор: {verdict.status}"
        )
        if contract is not None and contract.award_reduction_factor is not None:
            award = next(row for row in verdict.bids if row.is_award)
            from construction_os.calc.profit import calculate_profit
            from construction_os.references import RateType, get_rate

            at_award = calculate_profit(
                award.net,
                report.costs.production,
                report.costs.financial_fixed,
                report.costs.financial_share,
                get_rate(RateType.PROFIT_TAX, args.date).value,
            )
            from construction_os.calc.verdict import traffic_light

            award_status = traffic_light(at_award.profit_before_tax, award.net)
            summary_status = award_status
            print(
                f"При вашем снижении: прибыль {format_money_ru(at_award.profit_before_tax)}; "
                f"налог {format_money_ru(at_award.income_tax)}; "
                f"маржа {format_percent(at_award.margin_pct)}; {award_status}"
            )
    ten = next(row for row in verdict.bids if row.reduction == Decimal("0.10") and not row.is_award)
    print(
        f"ИТОГ: Выручка {format_money_ru(report.revenue_gross)}; "
        f"при снижении на 10% потеря {format_money_ru(-ten.delta_net)} без НДС; "
        f"{len(completeness.risks)} нормативных рисков не учтены; {summary_status}."
    )
    return 0

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from construction_os.calc import (
    CostArticle,
    CostEntry,
    ScenarioParam,
    apply_cost_scenario,
    calculate_profit,
    gross_from_net,
    min_revenue_for_margin,
    scenario_financial_share,
    scenario_revenue,
    summarize_costs,
)
from construction_os.cli_acts import configure_acts, run_acts
from construction_os.cli_calendar import configure_calendar, run_calendar
from construction_os.cli_cashflow import configure_cashflow, run_cashflow
from construction_os.cli_intake import configure_intake, run_intake
from construction_os.cli_penalty import configure_penalty, run_penalty
from construction_os.cli_whatif import configure_whatif, run_whatif
from construction_os.importers import (
    article_codes,
    parse_costs,
    parse_schedule,
    parse_vor,
    persist_costs,
    persist_schedule,
    persist_vor,
)
from construction_os.references import RateType, get_rate
from construction_os.reports import format_money, format_money_ru, format_percent
from construction_os.storage import make_engine
from construction_os.storage.economics import find_active_object, load_economics_report
from construction_os.storage.models import CostArticleRow, CostEntryRow
from construction_os.storage.queries import (
    object_lineage_ids,
    object_revenues,
    portfolio_revenue,
    verify_object,
)
from construction_os.storage.scenarios import create_scenario


def _decimal_arg(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="construction-os")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("import")
    p.add_argument("path")
    p.add_argument("--kind", choices=["vor", "schedule"], required=True)
    p.add_argument("--company", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--object", required=True)
    p.add_argument("--company", required=True)
    p = sub.add_parser("report")
    p.add_argument("--date", type=date.fromisoformat, required=True)
    p.add_argument("--company")
    p = sub.add_parser("debug-format", help="форматтер чисел; не выполняет расчёт объекта")
    p.add_argument("values", type=Decimal, nargs="*")
    costs = sub.add_parser("costs").add_subparsers(dest="costs_command", required=True)
    p = costs.add_parser("template")
    p.add_argument("--out", required=True)
    p = costs.add_parser("import")
    p.add_argument("path")
    p.add_argument("--company", required=True)
    for name in ("cost-report", "breakeven"):
        p = sub.add_parser(name)
        p.add_argument("--company", required=True)
        p.add_argument("--object", required=True)
        p.add_argument("--date", type=date.fromisoformat, required=True)
    p = sub.add_parser("scenario")
    p.add_argument("--company", required=True)
    p.add_argument("--object", required=True)
    p.add_argument("--date", type=date.fromisoformat, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--cost-multiplier", type=_decimal_arg)
    p.add_argument("--scope", choices=["all", "category", "cost_item"], default="all")
    p.add_argument("--scope-value")
    p.add_argument("--price-reduction", type=_decimal_arg)
    p.add_argument("--winter-surcharge-pct", type=_decimal_arg)
    p.add_argument("--financial-share-override", type=_decimal_arg)
    p.add_argument("--schedule-shift-days", type=_decimal_arg)
    configure_calendar(sub)
    configure_acts(sub)
    configure_penalty(sub)
    configure_whatif(sub)
    configure_cashflow(sub)
    configure_intake(sub)
    return parser


def _print_cost_report(report, on_date: date) -> None:
    complete = "полный" if report.costs and report.costs.complete else "неполный"
    print(
        f"{report.company.name} / {report.object_row.name} / {report.contract.number if report.contract else 'нет данных'} / {complete}"
    )
    print(f"Выручка с НДС: {format_money_ru(report.revenue_gross)}")
    print(f"Ставка НДС: {format_percent(report.vat_rate * Decimal('100'))}")
    print(f"Выручка без НДС: {format_money_ru(report.revenue_net)}")
    if report.costs is None or report.profit is None:
        print("Затраты: нет данных")
        return
    print(f"Затраты производственные: {format_money_ru(report.costs.production)}")
    for category in ("direct", "indirect", "other"):
        if category in report.costs.by_category:
            print(f"  {category}: {format_money_ru(report.costs.by_category[category])}")
    print(f"Затраты финансовые: {format_money_ru(report.profit.financial_costs)}")
    print(f"Итого затрат: {format_money_ru(report.profit.total_costs)}")
    print(f"Прибыль до налога: {format_money_ru(report.profit.profit_before_tax)}")
    tax = get_rate(RateType.PROFIT_TAX, on_date).value
    print(
        f"Налог на прибыль ({format_percent(tax * Decimal('100'))}): {format_money_ru(report.profit.income_tax)}"
    )
    print(f"Чистая прибыль: {format_money_ru(report.profit.net_profit)}")
    print(
        f"Маржа до налога: {format_percent(report.profit.margin_pct) if report.profit.margin_pct is not None else 'нет данных'}"
    )
    print(
        f"Точка безубыточности: {format_money_ru(report.breakeven.value) if report.breakeven.value is not None else report.breakeven.reason}"
    )
    print(
        f"Максимальное снижение цены: {format_percent(report.max_reduction.value) if report.max_reduction.value is not None else report.max_reduction.reason}"
    )
    for warning in report.costs.warnings:
        print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
    if report.costs.missing_articles:
        print("Нет данных: " + ", ".join(report.costs.missing_articles))


def _print_breakeven(report) -> int:
    if report.costs is None:
        print("нет данных")
        return 2
    print(
        f"Точка безубыточности: {format_money_ru(report.breakeven.value) if report.breakeven.value is not None else report.breakeven.reason}"
    )
    print(
        f"Максимальное снижение цены: {format_percent(report.max_reduction.value) if report.max_reduction.value is not None else report.max_reduction.reason}"
    )
    print("Маржа | Без НДС | С НДС")
    for margin in (Decimal("0"), Decimal("0.05"), Decimal("0.08"), Decimal("0.10")):
        x = min_revenue_for_margin(
            report.costs.production,
            report.costs.financial_fixed,
            report.costs.financial_share,
            margin,
        )
        if x.value is None:
            print(f"{margin}: {x.reason}")
            continue
        print(
            f"{format_percent(margin * Decimal('100'))} | {format_money_ru(x.value)} | {format_money_ru(gross_from_net(x.value, report.vat_rate))}"
        )
    return 0


def _scenario_params(args) -> list[ScenarioParam]:
    result = []
    if args.cost_multiplier is not None:
        result.append(
            ScenarioParam("cost_multiplier", args.cost_multiplier, args.scope, args.scope_value)
        )
    if args.price_reduction is not None:
        result.append(ScenarioParam("price_reduction", args.price_reduction))
    if args.winter_surcharge_pct is not None:
        result.append(
            ScenarioParam(
                "winter_surcharge_pct", args.winter_surcharge_pct, args.scope, args.scope_value
            )
        )
    if args.financial_share_override is not None:
        result.append(ScenarioParam("financial_share_override", args.financial_share_override))
    if args.schedule_shift_days is not None:
        result.append(ScenarioParam("schedule_shift_days", args.schedule_shift_days))
    return result


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "debug-format":
        for value in args.values:
            print(format_money(value))
        return 0
    if args.command == "costs" and args.costs_command == "template":
        from construction_os.importers.cost_template import make_template

        make_template(Path(args.out))
        print(f"cost template: {args.out}")
        return 0
    engine = make_engine()
    with Session(engine) as session:
        if args.command == "penalty":
            return run_penalty(args, session)
        if args.command == "acts":
            return run_acts(args, session)
        if args.command == "calendar":
            return run_calendar(args, session)
        if args.command == "whatif":
            return run_whatif(args, session)
        if args.command == "cash-flow":
            return run_cashflow(args, session)
        if args.command == "intake":
            return run_intake(args, session)
        if args.command == "import":
            result = (
                persist_vor(session, args.company, parse_vor(args.path), args.path)
                if args.kind == "vor"
                else persist_schedule(session, args.company, parse_schedule(args.path), args.path)
            )
            session.commit()
            print(
                f"Import: {'duplicate skipped' if result.skipped_duplicate else 'created'}; entities: {result.created_entities}; document: {result.document_id}"
            )
            return 0
        if args.command == "costs":
            parsed = parse_costs(args.path, article_codes(session))
            result = persist_costs(session, args.company, parsed, args.path)
            session.commit()
            print(
                f"Costs import: {'duplicate skipped' if result.skipped_duplicate else 'created'}; rows: {len(parsed.rows)}"
            )
            for warning in parsed.warnings:
                print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
            return 0
        if args.command == "verify":
            try:
                differences = verify_object(session, args.company, args.object)
            except LookupError as error:
                print(str(error))
                return 2
            print(f"Differences: {len(differences)}")
            for position, field in differences:
                print(f"{position}: {field}")
            return 0 if not differences else 1
        if args.command == "report":
            rows = object_revenues(session, args.date, args.company)
            if not rows:
                print("No imported objects")
                return 2
            for row in rows:
                print(
                    f"{row.company_name} / {row.object_name}: с НДС {format_money(row.revenue.gross)}; без НДС {format_money(row.revenue.net)}; НДС {format_money(row.revenue.vat)}"
                )
            portfolio = portfolio_revenue(rows, args.date)
            print(f"Портфель с НДС: {format_money(portfolio.gross)}")
            print(f"Портфель без НДС: {format_money(portfolio.net)}")
            print(f"Портфель НДС: {format_money(portfolio.vat)}")
            return 0
        report = load_economics_report(session, args.company, args.object, args.date)
        if args.command == "cost-report":
            _print_cost_report(report, args.date)
            return 0
        if args.command == "breakeven":
            return _print_breakeven(report)
        params = _scenario_params(args)
        if not params:
            print("сценарий без параметров: сравнивать не с чем")
            return 2
        company, obj = find_active_object(session, args.company, args.object)
        lineage = object_lineage_ids(session, obj)
        article_rows = list(
            session.scalars(select(CostArticleRow).where(CostArticleRow.is_active.is_(True)))
        )
        articles = {
            r.code: CostArticle(r.code, r.category, r.name, r.sort_order) for r in article_rows
        }
        rows = list(
            session.scalars(
                select(CostEntryRow).where(
                    CostEntryRow.company_id == company.id,
                    CostEntryRow.object_id.in_(lineage),
                    CostEntryRow.valid_to.is_(None),
                )
            )
        )
        entries = [
            CostEntry(
                r.article_code,
                r.amount,
                r.amount_type,
                r.rate_value,
                r.vat_mode,
                r.vat_rate,
                r.work_item_id,
            )
            for r in rows
        ]
        summary = summarize_costs(
            apply_cost_scenario(entries, articles, params),
            articles,
            default_vat_rate=report.vat_rate,
        )
        if summary is None or report.profit is None:
            print("нет данных")
            return 2
        new_revenue = scenario_revenue(report.revenue_net, params)
        share = scenario_financial_share(summary.financial_share, params)
        tax = get_rate(RateType.PROFIT_TAX, args.date).value
        after = calculate_profit(
            new_revenue, summary.production, summary.financial_fixed, share, tax
        )
        create_scenario(
            session, company.id, args.name, obj.id, obj.contract_id, args.date, params, "cli"
        )
        session.commit()
        print(
            f"До: прибыль {format_money_ru(report.profit.profit_before_tax)}, чистая {format_money_ru(report.profit.net_profit)}, маржа {format_percent(report.profit.margin_pct)}"
        )
        print(
            f"После: прибыль {format_money_ru(after.profit_before_tax)}, чистая {format_money_ru(after.net_profit)}, маржа {format_percent(after.margin_pct)}"
        )
        for p in params:
            print(
                f"{p.param_type}={p.param_value}; scope={p.scope}; scope_value={p.scope_value or '-'}"
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

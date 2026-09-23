"""Read-only CLI for point scenarios, sensitivity and algebraic goal seeking."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from construction_os.calc import CostArticle, CostEntry, ScenarioParam
from construction_os.calc.whatif import (
    evaluate,
    goal_seek,
    parse_multiplier,
    sensitivity,
    target_scope,
)
from construction_os.references import RateType, get_rate
from construction_os.reports import format_money_ru, format_percent
from construction_os.storage.economics import find_active_object, load_economics_report
from construction_os.storage.models import CostArticleRow, CostEntryRow
from construction_os.storage.queries import object_lineage_ids


def configure_whatif(sub) -> None:
    p = sub.add_parser("whatif", help="read-only sensitivity and goal-seek")
    p.add_argument("--company", required=True)
    p.add_argument("--object", required=True)
    p.add_argument("--date", type=date.fromisoformat, default=date.today())
    p.add_argument("--price-reduction")
    p.add_argument("--cost-multiplier", action="append", default=[])
    p.add_argument("--winter-surcharge-pct")
    p.add_argument("--scope", choices=["all", "category", "cost_item"], default="all")
    p.add_argument("--scope-value")
    p.add_argument("--financial-share")
    p.add_argument("--show-parameters", action="store_true")
    p.add_argument("--sensitivity", action="store_true")
    p.add_argument("--step", default="0.10")
    p.add_argument("--goal-seek")
    p.add_argument("--target-profit")


def _parameters(args, articles: dict[str, CostArticle]) -> list[ScenarioParam]:
    params: list[ScenarioParam] = []
    for raw in args.cost_multiplier:
        if "=" not in raw:
            raise ValueError(f"invalid cost-multiplier target: {raw}")
        target, value = raw.rsplit("=", 1)
        scope, scope_value = target_scope(target, articles)
        params.append(ScenarioParam("cost_multiplier", parse_multiplier(value), scope, scope_value))
    if args.price_reduction is not None:
        factor = parse_multiplier(args.price_reduction)
        params.append(ScenarioParam("price_reduction", Decimal("1") - factor))
    if args.winter_surcharge_pct is not None:
        pct = parse_multiplier(args.winter_surcharge_pct)
        params.append(ScenarioParam("winter_surcharge_pct", pct, args.scope, args.scope_value))
    if args.financial_share is not None:
        share = parse_multiplier(args.financial_share)
        params.append(ScenarioParam("financial_share_override", share))
    return params


def _print_values(name, result) -> None:
    print(f"## {name}")
    if result.profit is None:
        print("нет данных")
        return
    p = result.profit
    for label, value in (
        ("Выручка без НДС", p.revenue_net),
        ("Затраты производственные", p.costs_production),
        ("Затраты финансовые", p.financial_costs),
        ("Прибыль до налога", p.profit_before_tax),
        ("Налог", p.income_tax),
        ("Чистая прибыль", p.net_profit),
        ("Маржа %", p.margin_pct),
        ("Точка безубыточности", result.breakeven.value),
    ):
        if label == "Маржа %":
            display = format_percent(value) if value is not None else "нет данных"
        else:
            display = format_money_ru(value) if value is not None else "нет данных"
        print(f"{label}: {display}")


def run_whatif(args, session) -> int:
    try:
        company, obj = find_active_object(session, args.company, args.object)
        report = load_economics_report(session, args.company, args.object, args.date)
        article_rows = list(
            session.scalars(select(CostArticleRow).where(CostArticleRow.is_active.is_(True)))
        )
        articles = {
            r.code: CostArticle(r.code, r.category, r.name, r.sort_order) for r in article_rows
        }
        lineage = object_lineage_ids(session, obj)
        cost_rows = list(
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
            for r in cost_rows
        ]
        params = _parameters(args, articles)
        tax = get_rate(RateType.PROFIT_TAX, args.date).value
        base = evaluate(entries, articles, report.revenue_net, tax, vat_rate=report.vat_rate)
        after = evaluate(entries, articles, report.revenue_net, tax, params, report.vat_rate)
        print(f"{company.name} / {obj.name} / {args.date}")
        print(f"Полнота: {'полный' if base.costs and base.costs.complete else 'неполный'}")
        if base.costs and base.costs.missing_articles:
            print("Нет данных: " + ", ".join(base.costs.missing_articles))
        elif base.costs is None:
            print("Затраты: нет данных")
        print("## Параметры изменения")
        if not params:
            print("без изменений")
        for param in params:
            print(
                f"{param.param_type}={param.param_value}; "
                f"scope={param.scope}; scope_value={param.scope_value or '-'}"
            )
        _print_values("Базовый расчёт", base)
        _print_values("С изменениями", after)
        print("## Дельта")
        if base.profit and after.profit:
            for label, attr in (
                ("Выручка", "revenue_net"),
                ("Производственные", "costs_production"),
                ("Финансовые", "financial_costs"),
                ("Прибыль", "profit_before_tax"),
                ("Налог", "income_tax"),
                ("Чистая", "net_profit"),
                ("Маржа %", "margin_pct"),
            ):
                a = getattr(base.profit, attr)
                b = getattr(after.profit, attr)
                if a is not None and b is not None:
                    unit = " п.п." if attr == "margin_pct" else " ₽"
                    print(f"{label}: {b - a:+.2f}{unit}")
            if base.breakeven.value is not None and after.breakeven.value is not None:
                print(f"Безубыточность: {after.breakeven.value - base.breakeven.value:+.2f}")
        else:
            print("нет данных")
        if args.show_parameters:
            print("## Доступные параметры")
            print(f"Выручка с НДС: {format_money_ru(report.revenue_gross)}")
            print(f"Выручка без НДС: {format_money_ru(report.revenue_net)}")
            for code, article in sorted(
                articles.items(), key=lambda x: (x[1].sort_order or 0, x[0])
            ):
                value = base.costs.by_article.get(code) if base.costs else None
                print(
                    f"{code} | {article.category} | "
                    f"{format_money_ru(value) if value is not None else 'нет данных'}"
                )
            if base.costs:
                print(f"Финансовые фикс: {format_money_ru(base.costs.financial_fixed)}")
                print(f"Финансовые доля: {base.costs.financial_share}")
        if args.sensitivity:
            try:
                step = parse_multiplier(args.step)
            except ValueError:
                raise ValueError(f"invalid sensitivity step: {args.step}") from None
            if step <= 0:
                raise ValueError(f"invalid sensitivity step: {args.step}")
            print(f"## Чувствительность ±{step}")
            print("Параметр | прибыль −step | прибыль +step | Δ | ранг")
            for row in sensitivity(
                entries, articles, report.revenue_net, tax, step, report.vat_rate
            ):
                note = " (financial: множитель не действует)" if row.rank is None else ""
                print(
                    f"{row.parameter} | {row.minus_profit:.2f} | {row.plus_profit:.2f} "
                    f"| {row.delta:+.2f} | {row.rank if row.rank else '—'}{note}"
                )
        if args.goal_seek is not None or args.target_profit is not None:
            if args.goal_seek is None or args.target_profit is None:
                raise ValueError("goal-seek requires --goal-seek and --target-profit")
            if args.goal_seek != "price":
                try:
                    target_scope(args.goal_seek, articles)
                except ValueError:
                    raise ValueError(f"invalid goal-seek target: {args.goal_seek}") from None
            result = goal_seek(
                entries,
                articles,
                report.revenue_net,
                tax,
                args.goal_seek,
                parse_multiplier(args.target_profit),
                params,
                report.vat_rate,
            )
            print("## Обратный счёт")
            print(f"m*: {result.multiplier:.6f}")
            print(f"Проверочная прибыль: {result.checked_profit:.2f}")
            print(f"Остаток округления: {result.residual:.2f}")
        return 0
    except (ValueError, LookupError) as exc:
        print(str(exc))
        return 2

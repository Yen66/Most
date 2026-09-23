"""Pure read-only what-if calculations reusing the persisted scenario core."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from construction_os.calc.breakeven import ThresholdResult, breakeven_net
from construction_os.calc.costs import CostArticle, CostEntry, CostSummary, summarize_costs
from construction_os.calc.profit import ProfitResult, calculate_profit
from construction_os.calc.scenarios import (
    ScenarioParam,
    apply_cost_scenario,
    scenario_financial_share,
    scenario_revenue,
)
from construction_os.money import money

SIX_PLACES = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class WhatIfResult:
    costs: CostSummary | None
    profit: ProfitResult | None
    breakeven: ThresholdResult


@dataclass(frozen=True, slots=True)
class SensitivityRow:
    parameter: str
    minus_profit: Decimal
    plus_profit: Decimal
    delta: Decimal
    rank: int | None


@dataclass(frozen=True, slots=True)
class GoalSeekResult:
    target: str
    multiplier: Decimal
    checked_profit: Decimal
    residual: Decimal
    evaluation: WhatIfResult


def evaluate(
    entries: list[CostEntry],
    articles: dict[str, CostArticle],
    revenue_net: Decimal,
    tax_rate: Decimal,
    params: list[ScenarioParam] | None = None,
    vat_rate: Decimal | None = None,
) -> WhatIfResult:
    """All transformations go through calc.scenarios and the existing economics functions."""
    params = params or []
    costs = summarize_costs(
        apply_cost_scenario(entries, articles, params),
        articles,
        set(articles),
        default_vat_rate=vat_rate,
    )
    if costs is None:
        return WhatIfResult(None, None, ThresholdResult(None, "нет данных"))
    revenue = scenario_revenue(revenue_net, params)
    share = scenario_financial_share(costs.financial_share, params)
    return WhatIfResult(
        costs,
        calculate_profit(revenue, costs.production, costs.financial_fixed, share, tax_rate),
        breakeven_net(costs.production, costs.financial_fixed, share),
    )


def target_scope(target: str, articles: dict[str, CostArticle]) -> tuple[str, str | None]:
    if target == "all":
        return "all", None
    if target.startswith("category:") and target[9:] in {a.category for a in articles.values()}:
        return "category", target[9:]
    if target.startswith("item:") and target[5:] in articles:
        return "cost_item", target[5:]
    raise ValueError(f"invalid cost-multiplier target: {target}")


def parse_multiplier(value: str) -> Decimal:
    try:
        parsed = Decimal(value.replace(",", "."))
        if not parsed.is_finite():
            raise ValueError
        return parsed
    except (ValueError, ArithmeticError):
        raise ValueError(f"invalid multiplier: {value}") from None


def sensitivity(
    entries: list[CostEntry],
    articles: dict[str, CostArticle],
    revenue_net: Decimal,
    tax_rate: Decimal,
    step: Decimal,
    vat_rate: Decimal | None = None,
) -> list[SensitivityRow]:
    if not step.is_finite() or step <= 0:
        raise ValueError(f"invalid sensitivity step: {step}")
    base = evaluate(entries, articles, revenue_net, tax_rate, vat_rate=vat_rate)
    if base.profit is None or base.costs is None:
        return []
    targets = ["price", "all"]
    targets.extend("category:" + cat for cat in sorted({a.category for a in articles.values()}))
    targets.extend(
        "item:" + code
        for code, value in sorted(base.costs.by_article.items())
        if value != 0
    )
    rows: list[SensitivityRow] = []
    for target in targets:
        if target == "price":
            minus = [ScenarioParam("price_reduction", -step)]
            plus = [ScenarioParam("price_reduction", step)]
        else:
            scope, value = target_scope(target, articles)
            minus = [ScenarioParam("cost_multiplier", Decimal("1") - step, scope, value)]
            plus = [ScenarioParam("cost_multiplier", Decimal("1") + step, scope, value)]
        a = evaluate(entries, articles, revenue_net, tax_rate, minus, vat_rate)
        b = evaluate(entries, articles, revenue_net, tax_rate, plus, vat_rate)
        assert a.profit is not None and b.profit is not None
        delta = money(b.profit.profit_before_tax - base.profit.profit_before_tax)
        rows.append(
            SensitivityRow(
                target, a.profit.profit_before_tax, b.profit.profit_before_tax, delta, None
            )
        )
    rows.sort(key=lambda row: (-abs(row.delta), row.parameter))
    ranked = []
    rank = 0
    for row in rows:
        if row.delta != 0:
            rank += 1
        ranked.append(SensitivityRow(
            row.parameter, row.minus_profit, row.plus_profit, row.delta,
            rank if row.delta != 0 else None,
        ))
    return ranked


def goal_seek(
    entries: list[CostEntry],
    articles: dict[str, CostArticle],
    revenue_net: Decimal,
    tax_rate: Decimal,
    target: str,
    target_profit: Decimal,
    params: list[ScenarioParam] | None = None,
    vat_rate: Decimal | None = None,
) -> GoalSeekResult:
    """Closed-form target profit. Verify using the full, rounded production engine."""
    if target != "price":
        try:
            scope, value = target_scope(target, articles)
        except ValueError:
            raise ValueError(f"invalid goal-seek target: {target}") from None
    params = list(params or [])
    current = evaluate(entries, articles, revenue_net, tax_rate, params, vat_rate)
    if current.profit is None or current.costs is None:
        raise ValueError(f"goal-seek: no data for {target}")
    p = current.profit
    if target == "price":
        denominator = p.revenue_net * (Decimal("1") - p.financial_share)
        if denominator <= 0:
            raise ValueError(f"goal-seek: no data for {target}")
        exact = (p.costs_production + p.financial_fixed + target_profit) / denominator
        goal_param = ScenarioParam("price_reduction", Decimal("1") - exact.quantize(
            SIX_PLACES, rounding=ROUND_HALF_UP
        ))
    else:
        group = sum(
            (
                amount for code, amount in current.costs.by_article.items()
                if articles[code].category != "financial"
                and (scope == "all"
                     or (scope == "category" and articles[code].category == value)
                     or (scope == "cost_item" and code == value))
            ),
            Decimal("0"),
        )
        if group == 0:
            raise ValueError(f"goal-seek: no data for {target}")
        exact = (
            p.revenue_net - p.financial_costs - target_profit
            - (p.costs_production - group)
        ) / group
        goal_param = ScenarioParam(
            "cost_multiplier", exact.quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
            scope, value,
        )
    multiplier = exact.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
    verified = evaluate(entries, articles, revenue_net, tax_rate, [*params, goal_param], vat_rate)
    assert verified.profit is not None
    actual = verified.profit.profit_before_tax
    return GoalSeekResult(target, multiplier, actual, money(abs(actual - target_profit)), verified)

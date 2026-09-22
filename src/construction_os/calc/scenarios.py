from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from construction_os.money import money

from .costs import CostArticle, CostEntry


@dataclass(frozen=True, slots=True)
class ScenarioParam:
    param_type: str
    param_value: Decimal
    scope: str = "all"
    scope_value: str | None = None


def _matches(entry: CostEntry, article: CostArticle, param: ScenarioParam) -> bool:
    if article.category == "financial":
        return False
    if param.scope == "all":
        return True
    if param.scope == "category":
        return article.category == param.scope_value
    return article.code == param.scope_value


def apply_cost_scenario(
    entries: list[CostEntry], articles: dict[str, CostArticle], params: list[ScenarioParam]
) -> list[CostEntry]:
    result = list(entries)
    for param in params:
        if param.param_type not in {"cost_multiplier", "winter_surcharge_pct"}:
            continue
        multiplier = (
            param.param_value
            if param.param_type == "cost_multiplier"
            else Decimal("1") + param.param_value
        )
        result = [
            replace(e, amount=money(e.amount * multiplier))
            if e.amount is not None and _matches(e, articles[e.article_code], param)
            else e
            for e in result
        ]
    return result


def scenario_revenue(revenue_net: Decimal, params: list[ScenarioParam]) -> Decimal:
    value = revenue_net
    for param in params:
        if param.param_type == "price_reduction":
            value *= Decimal("1") - param.param_value
    return money(value)


def scenario_financial_share(base: Decimal, params: list[ScenarioParam]) -> Decimal:
    values = [p.param_value for p in params if p.param_type == "financial_share_override"]
    return values[-1] if values else base


def validate_scenario_param(param: ScenarioParam, articles: dict[str, CostArticle]) -> None:
    if (
        param.param_type == "schedule_shift_days"
        and param.param_value != param.param_value.to_integral_value()
    ):
        raise ValueError("количество дней должно быть целым")
    if param.scope == "cost_item" and param.scope_value not in articles:
        raise ValueError(f"неизвестная статья затрат: {param.scope_value}")
    if param.scope == "category" and param.scope_value not in {
        a.category for a in articles.values()
    }:
        raise ValueError(f"неизвестная категория затрат: {param.scope_value}")

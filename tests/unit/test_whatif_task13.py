from __future__ import annotations

from decimal import Decimal

import pytest

from construction_os.calc.costs import CostArticle, CostEntry
from construction_os.calc.scenarios import ScenarioParam
from construction_os.calc.whatif import (
    evaluate, goal_seek, parse_multiplier, sensitivity, target_scope,
)
from construction_os.references.cost_articles import DEFAULT_COST_ARTICLES

D = Decimal


@pytest.fixture
def example():
    articles = {
        code: CostArticle(code, cat, name, i)
        for i, (code, cat, name) in enumerate(DEFAULT_COST_ARTICLES, 1)
    }
    entries = [
        CostEntry("MAT", D("500000"), vat_mode="net"),
        CostEntry("LAB", D("250000"), vat_mode="net"),
        CostEntry("MACH_OWN", D("70000"), vat_mode="net"),
        CostEntry("OVR_SITE", D("50000"), vat_mode="net"),
        CostEntry("BANK_GUAR", D("27000"), vat_mode="net"),
    ]
    return entries, articles


def P(kind, value, scope="all", scope_value=None):
    return ScenarioParam(kind, D(value), scope, scope_value)


@pytest.mark.parametrize(
    "case,params,revenue,production,profit,tax,net,margin",
    [
        ("S1", [], "1000000", "870000", "103000", "25750", "77250", "10.30"),
        ("S2", [P("cost_multiplier", "1.10", "cost_item", "MAT")],
         "1000000", "920000", "53000", "13250", "39750", "5.30"),
        ("S3", [P("price_reduction", "0.08")],
         "920000", "870000", "23000", "5750", "17250", "2.50"),
        ("S4", [P("price_reduction", "0.08"), P("cost_multiplier", "1.10")],
         "920000", "957000", "-64000", "0", "-64000", "-6.96"),
        ("S5", [P("cost_multiplier", "1.10")],
         "1000000", "957000", "16000", "4000", "12000", "1.60"),
        ("S6", [P("price_reduction", "0.08"),
                P("cost_multiplier", "1.10", "cost_item", "MAT")],
         "920000", "920000", "-27000", "0", "-27000", "-2.93"),
        ("S7", [P("financial_share_override", "0.027")],
         "1000000", "870000", "76000", "19000", "57000", "7.60"),
        ("S8", [P("cost_multiplier", "1.10", "category", "direct")],
         "1000000", "952000", "21000", "5250", "15750", "2.10"),
        ("S9", [P("cost_multiplier", "1.05", "cost_item", "MAT")],
         "1000000", "895000", "78000", "19500", "58500", "7.80"),
    ],
)
def test_F5_scenarios(example, case, params, revenue, production, profit, tax, net, margin):
    entries, articles = example
    result = evaluate(entries, articles, D("1000000"), D("0.25"), params, D("0.22"))
    assert result.profit is not None, case
    p = result.profit
    assert (p.revenue_net, p.costs_production, p.profit_before_tax,
            p.income_tax, p.net_profit, p.margin_pct) == (
        D(revenue), D(production), D(profit), D(tax), D(net), D(margin)
    )


@pytest.mark.parametrize(
    "target,profit,multiplier,checked,residual",
    [
        ("item:MAT", "0", "1.206000", "0.00", "0.00"),
        ("price", "0", "0.897000", "0.00", "0.00"),
        ("all", "0", "1.118391", "-0.17", "0.17"),
        ("item:MAT", "50000", "1.106000", "50000.00", "0.00"),
    ],
)
def test_F5b_goal_seek(example, target, profit, multiplier, checked, residual):
    entries, articles = example
    result = goal_seek(
        entries, articles, D("1000000"), D("0.25"), target, D(profit), vat_rate=D("0.22")
    )
    assert result.multiplier == D(multiplier)
    assert result.checked_profit == D(checked)
    assert result.residual == D(residual)


@pytest.mark.parametrize(
    "target,delta,rank",
    [
        ("price", "-100000", 1),
        ("all", "-87000", 2),
        ("category:direct", "-82000", 3),
        ("item:MAT", "-50000", 4),
        ("item:LAB", "-25000", 5),
        ("item:MACH_OWN", "-7000", 6),
        ("item:OVR_SITE", "-5000", 7),
        ("item:BANK_GUAR", "0", None),
        ("category:financial", "0", None),
    ],
)
def test_F6_sensitivity_ranking(example, target, delta, rank):
    entries, articles = example
    rows = sensitivity(entries, articles, D("1000000"), D("0.25"), D("0.10"))
    found = next(row for row in rows if row.parameter == target)
    assert found.delta == D(delta)
    assert found.rank == rank


def test_F6_additive_identity(example):
    entries, articles = example
    rows = sensitivity(entries, articles, D("1000000"), D("0.25"), D("0.10"))
    by_name = {row.parameter: row.delta for row in rows}
    assert sum(
        (by_name["item:" + code] for code in ("MAT", "LAB", "MACH_OWN", "OVR_SITE")),
        D("0"),
    ) == by_name["all"] == D("-87000")


def test_F6_minus_step_all(example):
    entries, articles = example
    rows = sensitivity(entries, articles, D("1000000"), D("0.25"), D("0.10"))
    assert next(row for row in rows if row.parameter == "all").minus_profit == D("190000")


def test_F5_goal_seek_equals_breakeven(example):
    entries, articles = example
    base = evaluate(entries, articles, D("1000000"), D("0.25"))
    result = goal_seek(entries, articles, D("1000000"), D("0.25"), "price", D("0"))
    assert result.multiplier * D("1000000") == base.breakeven.value


def test_F5_financial_share_additive(example):
    entries, articles = example
    result = evaluate(
        entries, articles, D("1000000"), D("0.25"),
        [P("financial_share_override", "0.027")],
    )
    assert result.breakeven.value == D("921891.06")
    assert result.profit.financial_costs == D("54000")


def test_repeated_multipliers_round_each_step(example):
    entries, articles = example
    params = [P("cost_multiplier", "1.10", "cost_item", "MAT"),
              P("cost_multiplier", "1.05", "cost_item", "MAT")]
    result = evaluate(entries, articles, D("1000000"), D("0.25"), params)
    assert result.costs.by_article["MAT"] == D("577500.00")


def test_winter_surcharge_reuses_core(example):
    entries, articles = example
    result = evaluate(
        entries, articles, D("1000000"), D("0.25"),
        [P("winter_surcharge_pct", "0.03")],
    )
    assert result.profit.profit_before_tax == D("76900")


def test_no_cost_data_is_explicit(example):
    _, articles = example
    result = evaluate([], articles, D("1000000"), D("0.25"))
    assert result.profit is None and result.costs is None


def test_financial_multiplier_never_changes_financial(example):
    entries, articles = example
    result = evaluate(
        entries, articles, D("1000000"), D("0.25"),
        [P("cost_multiplier", "1.10", "cost_item", "BANK_GUAR")],
    )
    assert result.profit.profit_before_tax == D("103000")


@pytest.mark.parametrize("target", ["bad", "category:unknown", "item:BAD", "item:", "category:"])
def test_invalid_cost_target(example, target):
    with pytest.raises(ValueError, match="invalid cost-multiplier target:"):
        target_scope(target, example[1])


@pytest.mark.parametrize("value", ["not-a-number", "NaN", "Infinity"])
def test_invalid_multiplier(value):
    with pytest.raises(ValueError, match="invalid multiplier:"):
        parse_multiplier(value)


@pytest.mark.parametrize("step", ["0", "-0.1"])
def test_invalid_sensitivity_step(example, step):
    with pytest.raises(ValueError, match="invalid sensitivity step:"):
        sensitivity(example[0], example[1], D("1000000"), D("0.25"), D(step))


def test_goal_seek_unknown_target(example):
    with pytest.raises(ValueError, match="invalid goal-seek target:"):
        goal_seek(example[0], example[1], D("1000000"), D("0.25"), "bad", D("0"))


def test_goal_seek_empty_group(example):
    with pytest.raises(ValueError, match="goal-seek: no data for item:MAT"):
        goal_seek(
            [CostEntry("LAB", D("1"), vat_mode="net")], example[1],
            D("1000000"), D("0.25"), "item:MAT", D("0"),
        )


def test_scenario_identity_for_three_cases(example):
    from construction_os.calc import apply_cost_scenario, calculate_profit, summarize_costs
    from construction_os.calc.scenarios import scenario_financial_share, scenario_revenue

    entries, articles = example
    for params in (
        [P("cost_multiplier", "1.10", "cost_item", "MAT")],
        [P("price_reduction", "0.08"), P("cost_multiplier", "1.10")],
        [P("cost_multiplier", "1.10", "category", "direct")],
    ):
        actual = evaluate(entries, articles, D("1000000"), D("0.25"), params)
        summary = summarize_costs(
            apply_cost_scenario(entries, articles, params), articles
        )
        stored = calculate_profit(
            scenario_revenue(D("1000000"), params),
            summary.production, summary.financial_fixed,
            scenario_financial_share(summary.financial_share, params), D("0.25"),
        )
        assert actual.profit == stored

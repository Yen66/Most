from datetime import date
from decimal import Decimal
import pytest
from construction_os.calc import (
    CostArticle,
    CostEntry,
    ScenarioParam,
    apply_cost_scenario,
    breakeven_net,
    calculate_profit,
    gross_from_net,
    max_price_reduction,
    min_revenue_for_margin,
    scenario_financial_share,
    scenario_revenue,
    summarize_costs,
)
from construction_os.references import RateType, get_rate

D = Decimal
ARTICLES = {
    "MAT": CostArticle("MAT", "direct", "Материалы"),
    "LAB": CostArticle("LAB", "direct", "ФОТ"),
    "MACH_OWN": CostArticle("MACH_OWN", "direct", "Техника"),
    "OVR_SITE": CostArticle("OVR_SITE", "indirect", "Накладные"),
    "BANK_GUAR": CostArticle("BANK_GUAR", "financial", "Гарантия"),
    "FINANCE": CostArticle("FINANCE", "financial", "Финансирование"),
    "OTHER": CostArticle("OTHER", "other", "Прочие"),
}


def base_entries(fin_share=False):
    rows = [
        CostEntry("MAT", D("500000"), vat_mode="net"),
        CostEntry("LAB", D("250000"), vat_mode="net"),
        CostEntry("MACH_OWN", D("70000"), vat_mode="net"),
        CostEntry("OVR_SITE", D("50000"), vat_mode="net"),
    ]
    rows.append(
        CostEntry("FINANCE", None, "share_of_revenue", D("0.027"), "net")
        if fin_share
        else CostEntry("BANK_GUAR", D("27000"), vat_mode="net")
    )
    return rows


def summary(fin_share=False, extra=None):
    return summarize_costs(base_entries(fin_share) + (extra or []), ARTICLES)


def test_case1_reference():
    s = summary()
    r = calculate_profit(
        D("1000000"),
        s.production,
        s.financial_fixed,
        s.financial_share,
        get_rate(RateType.PROFIT_TAX, date(2026, 9, 20)).value,
    )
    assert (r.total_costs, r.profit_before_tax, r.income_tax, r.net_profit, r.margin_pct) == (
        D("897000.00"),
        D("103000.00"),
        D("25750.00"),
        D("77250.00"),
        D("10.30"),
    )
    assert breakeven_net(s.production, s.financial_fixed, s.financial_share).value == D("897000.00")


def test_case2_reference():
    s = summary(True)
    r = calculate_profit(
        D("1000000"), s.production, s.financial_fixed, s.financial_share, D("0.25")
    )
    assert r.financial_costs == D("27000.00") and breakeven_net(
        s.production, s.financial_fixed, s.financial_share
    ).value == D("894141.83")


def test_other_is_not_lost():
    s = summary(extra=[CostEntry("OTHER", D("12345.67"), vat_mode="net")])
    r = calculate_profit(
        D("1000000"), s.production, s.financial_fixed, s.financial_share, D("0.25")
    )
    assert (
        s.production == D("882345.67")
        and r.net_profit == D("67990.75")
        and any("не классифицирована" in w for w in s.warnings)
    )


def test_gross_cost_extracts_vat():
    assert summarize_costs(
        [CostEntry("MAT", D("122000"), vat_mode="gross")], ARTICLES, default_vat_rate=D("0.22")
    ).production == D("100000.00")


def test_unknown_vat_warns():
    assert (
        summarize_costs(
            [CostEntry("MAT", D("100"), vat_mode="unknown")], ARTICLES
        ).unknown_vat_count
        == 1
    )


def test_no_costs_is_none():
    assert summarize_costs([], ARTICLES) is None


def test_financial_share_invalid_denominator():
    assert breakeven_net(D("1"), D("0"), D("1")).value is None


def test_zero_revenue_reduction_none():
    assert max_price_reduction(D("0"), D("1")).value is None


@pytest.mark.parametrize(
    "margin,net,gross",
    [
        ("0", "897000.00", "1094340.00"),
        ("0.05", "944210.53", "1151936.85"),
        ("0.08", "975000.00", "1189500.00"),
        ("0.10", "996666.67", "1215933.34"),
    ],
)
def test_case1_minimum_prices(margin, net, gross):
    x = min_revenue_for_margin(D("870000"), D("27000"), D("0"), D(margin))
    assert x.value == D(net)
    assert gross_from_net(x.value, D("0.22")) == D(gross)


@pytest.mark.parametrize(
    "margin,net,gross",
    [
        ("0", "894141.83", "1090853.03"),
        ("0.05", "942578.55", "1149945.83"),
        ("0.08", "974244.12", "1188577.83"),
        ("0.10", "996563.57", "1215807.56"),
    ],
)
def test_case2_minimum_prices(margin, net, gross):
    x = min_revenue_for_margin(D("870000"), D("0"), D("0.027"), D(margin))
    assert x.value == D(net)
    assert gross_from_net(x.value, D("0.22")) == D(gross)


@pytest.mark.parametrize(
    "reduction,profit",
    [
        ("0", "103000"),
        ("0.05", "53000"),
        ("0.10", "3000"),
        ("0.103", "0"),
        ("0.11", "-7000"),
        ("0.20", "-97000"),
    ],
)
def test_case1_sensitivity(reduction, profit):
    r = calculate_profit(
        D("1000000") * (D("1") - D(reduction)), D("870000"), D("27000"), D("0"), D("0.25")
    )
    assert r.profit_before_tax == D(profit).quantize(D("0.01"))


@pytest.mark.parametrize(
    "reduction,financial,profit",
    [("0.05", "25650", "54350"), ("0.10", "24300", "5700"), ("0.11", "24030", "-4030")],
)
def test_case2_sensitivity(reduction, financial, profit):
    r = calculate_profit(
        D("1000000") * (D("1") - D(reduction)), D("870000"), D("0"), D("0.027"), D("0.25")
    )
    assert r.financial_costs == D(financial).quantize(D("0.01"))
    assert r.profit_before_tax == D(profit).quantize(D("0.01"))


def test_mat_scenario():
    s = summarize_costs(
        apply_cost_scenario(
            base_entries(),
            ARTICLES,
            [ScenarioParam("cost_multiplier", D("1.10"), "cost_item", "MAT")],
        ),
        ARTICLES,
    )
    assert calculate_profit(
        D("1000000"), s.production, s.financial_fixed, s.financial_share, D("0.25")
    ).profit_before_tax == D("53000.00")


def test_all_cost_scenario_does_not_touch_financial():
    s = summarize_costs(
        apply_cost_scenario(
            base_entries(), ARTICLES, [ScenarioParam("cost_multiplier", D("1.10"))]
        ),
        ARTICLES,
    )
    assert s.production == D("957000.00") and s.financial_fixed == D("27000.00")


def test_combined_scenario():
    params = [
        ScenarioParam("cost_multiplier", D("1.10")),
        ScenarioParam("price_reduction", D("0.08")),
    ]
    s = summarize_costs(apply_cost_scenario(base_entries(), ARTICLES, params), ARTICLES)
    r = calculate_profit(
        scenario_revenue(D("1000000"), params),
        s.production,
        s.financial_fixed,
        s.financial_share,
        D("0.25"),
    )
    assert r.profit_before_tax == D("-64000.00") and r.income_tax == D("0.00")


def test_winter_surcharge():
    s = summarize_costs(
        apply_cost_scenario(
            base_entries(), ARTICLES, [ScenarioParam("winter_surcharge_pct", D("0.03"))]
        ),
        ARTICLES,
    )
    assert s.production == D("896100.00")


def test_financial_override():
    assert scenario_financial_share(
        D("0.01"), [ScenarioParam("financial_share_override", D("0.027"))]
    ) == D("0.027")


@pytest.mark.parametrize(
    "production,fixed,share,margin",
    [
        ("100", "0", "0", "0"),
        ("100", "10", "0", "0.05"),
        ("870000", "27000", "0", "0.08"),
        ("870000", "0", "0.027", "0.10"),
        ("1", "0", "0.5", "0.1"),
        ("10", "5", "0.2", "0.3"),
        ("0", "1", "0", "0"),
        ("999.99", "1.01", "0.01", "0.05"),
        ("100000", "2000", "0.03", "0.08"),
        ("500", "50", "0.05", "0.1"),
        ("100", "0", "1", "0"),
        ("100", "0", "0.95", "0.05"),
        ("10", "0", "0", "1"),
        ("10", "0", "0.2", "0.8"),
        ("1234.56", "78.90", "0.02", "0.04"),
        ("700", "30", "0.07", "0.12"),
        ("800", "0", "0.1", "0"),
        ("0.01", "0", "0", "0"),
        ("1000000", "27000", "0", "0.05"),
        ("870000", "0", "0.027", "0"),
    ],
)
def test_threshold_identity_grid(production, fixed, share, margin):
    p, f, s, m = map(D, (production, fixed, share, margin))
    x = min_revenue_for_margin(p, f, s, m)
    if D("1") - m - s <= 0:
        assert x.value is None
        return
    assert x.value is not None
    if m == 0:
        assert x.value == breakeven_net(p, f, s).value

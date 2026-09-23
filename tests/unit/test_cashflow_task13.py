from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from construction_os.calc.cashflow import Flow, daily_balances, financing_cost, gap_report

D = Decimal
T = date.fromisoformat


def cases():
    base = [
        Flow(T("2026-09-15"), "outflow", D("600000"), "MAT"),
        Flow(T("2026-09-30"), "outflow", D("200000"), "LAB"),
        Flow(T("2026-10-08"), "inflow", D("1000000"), "act_payment"),
    ]
    return {
        "CF1": (base, T("2026-09-15"), T("2026-10-31")),
        "CF2": (
            [Flow(T("2026-09-01"), "inflow", D("300000"), "advance"), *base],
            T("2026-09-01"), T("2026-10-31"),
        ),
        "CF3": (
            [Flow(T("2026-09-20"), "outflow", D("960000"), "SUB"),
             Flow(T("2026-10-08"), "inflow", D("950000"), "act_payment")],
            T("2026-09-20"), T("2026-10-31"),
        ),
        "CF4": (
            [Flow(T("2026-10-01"), "outflow", D("800000"), "MAT"),
             Flow(T("2026-10-20"), "inflow", D("1000000"), "act_payment", "fact")],
            T("2026-10-01"), T("2026-10-31"),
        ),
        "CF5": (
            [Flow(T("2026-09-01"), "inflow", D("500000"), "advance"),
             Flow(T("2026-09-20"), "outflow", D("400000"), "MAT")],
            T("2026-09-01"), T("2026-09-30"),
        ),
    }


EXPECTED = {
    "CF1": (23, D("800000"), T("2026-09-30"), T("2026-09-15"),
            T("2026-10-08"), D("5906.85"), D("200000")),
    "CF2": (23, D("500000"), T("2026-09-30"), T("2026-09-15"),
            T("2026-10-08"), D("3260.27"), D("500000")),
    "CF3": (42, D("960000"), T("2026-09-20"), T("2026-09-20"),
            None, D("6720.00"), D("-10000")),
    "CF4": (19, D("800000"), T("2026-10-01"), T("2026-10-01"),
            T("2026-10-20"), D("5830.14"), D("200000")),
    "CF5": (0, D("0"), None, None, None, D("0.00"), D("100000")),
}


@pytest.mark.parametrize("name", list(EXPECTED))
@pytest.mark.parametrize(
    "field,index",
    [
        ("deficit_days", 0), ("max_deficit", 1),
        ("max_deficit_date", 2), ("first_negative_date", 3),
        ("recovered_date", 4),
    ],
)
def test_F1_gap_metrics(name, field, index):
    flows, start, end = cases()[name]
    actual = gap_report(daily_balances(flows, start, end))
    assert getattr(actual, field) == EXPECTED[name][index]


@pytest.mark.parametrize("name", list(EXPECTED))
def test_F1_financing_cost(name):
    flows, start, end = cases()[name]
    assert financing_cost(daily_balances(flows, start, end), D("0.14")) == EXPECTED[name][5]


@pytest.mark.parametrize("name", list(EXPECTED))
def test_F1_last_balance_equals_signed_sum(name):
    flows, start, end = cases()[name]
    balances = daily_balances(flows, start, end)
    signed = sum(
        (f.amount if f.direction == "inflow" else -f.amount for f in flows), D("0")
    )
    assert balances[-1].balance == EXPECTED[name][6] == signed


def test_CF2_advance_financing_savings():
    a = cases()
    cf1 = financing_cost(daily_balances(*a["CF1"]), D("0.14"))
    cf2 = financing_cost(daily_balances(*a["CF2"]), D("0.14"))
    assert cf1 - cf2 == D("2646.58")


def test_zero_balance_not_deficit():
    flows = [
        Flow(T("2026-09-01"), "outflow", D("100")),
        Flow(T("2026-09-02"), "inflow", D("100")),
    ]
    gap = gap_report(daily_balances(flows, T("2026-09-01"), T("2026-09-02")))
    assert gap.deficit_days == 1
    assert gap.recovered_date == T("2026-09-02")


def test_future_flows_do_not_affect_window():
    flows, start, end = cases()["CF1"]
    future = Flow(T("2026-11-01"), "outflow", D("9000000"))
    assert daily_balances([*flows, future], start, end) == daily_balances(flows, start, end)


@pytest.mark.parametrize("rate", ["0", "-0.01"])
def test_invalid_financing_rate(rate):
    with pytest.raises(ValueError, match="rate must be positive"):
        financing_cost([], D(rate))


def test_invalid_flow_direction():
    with pytest.raises(ValueError, match="invalid direction"):
        daily_balances(
            [Flow(T("2026-09-01"), "other", D("1"))],
            T("2026-09-01"), T("2026-09-01"),
        )


def test_reversed_window():
    with pytest.raises(ValueError, match="end earlier"):
        daily_balances([], T("2026-09-02"), T("2026-09-01"))

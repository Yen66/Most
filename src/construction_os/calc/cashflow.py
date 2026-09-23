"""Deterministic calendar-day cash-flow arithmetic, without persistence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from construction_os.money import money


@dataclass(frozen=True, slots=True)
class Flow:
    flow_date: date
    direction: str
    amount: Decimal
    category: str = ""
    plan_or_fact: str = "plan"
    source_kind: str | None = None


@dataclass(frozen=True, slots=True)
class DailyBalance:
    day: date
    inflow: Decimal
    outflow: Decimal
    balance: Decimal


@dataclass(frozen=True, slots=True)
class GapReport:
    deficit_days: int
    max_deficit: Decimal
    max_deficit_date: date | None
    first_negative_date: date | None
    recovered_date: date | None


def daily_balances(flows: list[Flow], start: date, end: date) -> list[DailyBalance]:
    if end < start:
        raise ValueError("cash-flow: end earlier than start")
    movements: dict[date, list[Decimal]] = {}
    for flow in flows:
        if not start <= flow.flow_date <= end:
            continue
        if flow.direction not in {"inflow", "outflow"} or flow.amount <= 0:
            raise ValueError("cash-flow: invalid direction or amount")
        amounts = movements.setdefault(flow.flow_date, [Decimal("0"), Decimal("0")])
        amounts[0 if flow.direction == "inflow" else 1] += flow.amount
    result: list[DailyBalance] = []
    balance = Decimal("0")
    day = start
    while day <= end:
        inflow, outflow = movements.get(day, [Decimal("0"), Decimal("0")])
        balance = money(balance + inflow - outflow)
        result.append(DailyBalance(day, money(inflow), money(outflow), balance))
        day += timedelta(days=1)
    return result


def gap_report(balances: list[DailyBalance]) -> GapReport:
    negatives = [row for row in balances if row.balance < 0]
    if not negatives:
        return GapReport(0, Decimal("0.00"), None, None, None)
    maximum = max(-row.balance for row in negatives)
    maximum_day = next(row.day for row in negatives if -row.balance == maximum)
    last_negative = negatives[-1].day
    recovered = next(
        (row.day for row in balances if row.day > last_negative and row.balance >= 0),
        None,
    )
    return GapReport(len(negatives), money(maximum), maximum_day, negatives[0].day, recovered)


def financing_cost(balances: list[DailyBalance], rate: Decimal) -> Decimal:
    if not rate.is_finite() or rate <= 0:
        raise ValueError("cash-flow: financing rate must be positive")
    deficit_day_sum = sum((-row.balance for row in balances if row.balance < 0), Decimal("0"))
    return money(deficit_day_sum * rate / Decimal("365"))

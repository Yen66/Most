from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from construction_os.money.core import money
from construction_os.references.rates import (
    INITIAL_RATES,
    RateType,
    ReferenceRate,
    get_rate,
)

PENALTY_DIVISOR = Decimal(300)  # 44-FZ article 34 part 5: 1/300 key rate
NO_CAP_WARNING = (
    "потолок: нет данных в договоре; нормативный потолок 44-ФЗ не установлен; "
    "возможно снижение по ст. 333 ГК РФ"
)


@dataclass(frozen=True, slots=True)
class DebtSegment:
    debt: Decimal
    start: date
    end: date
    days: int
    closed_by_payment: bool


@dataclass(frozen=True, slots=True)
class PenaltySegment:
    debt: Decimal
    start: date
    end: date
    days: int
    rate: Decimal
    amount: Decimal
    rate_effective_from: date
    document_number: str | None


@dataclass(frozen=True, slots=True)
class RateHistoryEntry:
    start: date
    end: date
    rate: Decimal
    document_number: str | None


@dataclass(frozen=True, slots=True)
class PenaltyResult:
    segments: tuple[PenaltySegment, ...]
    total: Decimal
    total_uncapped: Decimal
    rate_used: Decimal
    rate_effective_from: date
    document_number: str | None
    cap_applied: bool
    cap_value: Decimal | None
    cap_reached_day: int | None
    warnings: tuple[str, ...]
    rate_history: tuple[RateHistoryEntry, ...]
    days: int


def delay_days(due_on: date, paid_on: date | None = None, as_of: date | None = None) -> int:
    """Calendar days after due_on, including the settlement/report date."""
    if as_of is None:
        raise ValueError("as_of is required")
    end = paid_on if paid_on is not None and paid_on <= as_of else as_of
    return max((end - due_on).days, 0)


def penalty_segments(
    amount: Decimal,
    due_on: date,
    paid_on: date | None = None,
    paid_amount: Decimal | None = None,
    as_of: date | None = None,
) -> tuple[DebtSegment, ...]:
    if as_of is None:
        raise ValueError("as_of is required")
    if (paid_on is None) != (paid_amount is None):
        raise ValueError("paid_on and paid_amount must be provided together")
    if paid_amount is not None and (paid_amount <= 0 or paid_amount > amount):
        raise ValueError("invalid paid_amount")
    if as_of <= due_on:
        return ()
    if paid_on is None or paid_on > as_of:
        return (
            DebtSegment(
                amount,
                due_on + timedelta(days=1),
                as_of,
                (as_of - due_on).days,
                False,
            ),
        )
    segments = []
    if paid_on > due_on:
        segments.append(
            DebtSegment(
                amount,
                due_on + timedelta(days=1),
                paid_on,
                (paid_on - due_on).days,
                True,
            )
        )
    remaining = amount - paid_amount
    after = max(paid_on, due_on)
    if remaining > 0 and as_of > after:
        segments.append(
            DebtSegment(
                remaining,
                after + timedelta(days=1),
                as_of,
                (as_of - after).days,
                False,
            )
        )
    return tuple(segments)


def penalty_for_segment(debt: Decimal, days: int, rate: Decimal) -> Decimal:
    """One ROUND_HALF_UP operation per segment, no rounded daily rate."""
    return money(debt * rate * Decimal(days) / PENALTY_DIVISOR)


def rate_history_between(
    start: date,
    end: date,
    rates: tuple[ReferenceRate, ...] = INITIAL_RATES,
) -> tuple[RateHistoryEntry, ...]:
    if end < start:
        return ()
    result = []
    for item in rates:
        if item.rate_type != RateType.KEY_RATE:
            continue
        first = max(start, item.valid_from)
        last = min(end, item.valid_to or end)
        if first <= last:
            result.append(RateHistoryEntry(first, last, item.value, item.document_number))
    return tuple(result)


def calculate_penalty(
    amount: Decimal,
    due_on: date,
    *,
    as_of: date,
    paid_on: date | None = None,
    paid_amount: Decimal | None = None,
    penalty_cap_pct: Decimal | None = None,
    rate_date: date | None = None,
) -> PenaltyResult:
    """44-FZ art. 34(5): settlement-date rate, calendar days, contract cap only."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    if penalty_cap_pct is not None and penalty_cap_pct < 0:
        raise ValueError("penalty_cap_pct cannot be negative")
    raw_segments = penalty_segments(amount, due_on, paid_on, paid_amount, as_of)
    final_rate_date = rate_date or (raw_segments[-1].end if raw_segments else as_of)
    selected = get_rate(RateType.KEY_RATE, final_rate_date)
    segments = []
    for raw in raw_segments:
        on_date = rate_date or (raw.end if raw.closed_by_payment else as_of)
        rate = get_rate(RateType.KEY_RATE, on_date)
        segments.append(
            PenaltySegment(
                raw.debt,
                raw.start,
                raw.end,
                raw.days,
                rate.value,
                penalty_for_segment(raw.debt, raw.days, rate.value),
                rate.valid_from,
                rate.document_number,
            )
        )
    uncapped = money(sum((s.amount for s in segments), Decimal("0")))
    cap = money(amount * penalty_cap_pct) if penalty_cap_pct is not None else None
    total = min(uncapped, cap) if cap is not None else uncapped
    cap_applied = cap is not None and uncapped >= cap
    cap_day = None
    if cap_applied:
        cumulative = Decimal("0")
        elapsed = 0
        for segment in segments:
            for n in range(1, segment.days + 1):
                if cumulative + penalty_for_segment(segment.debt, n, segment.rate) >= cap:
                    cap_day = elapsed + n
                    break
            if cap_day is not None:
                break
            cumulative += segment.amount
            elapsed += segment.days
    final_day = max(segment.end for segment in segments) if segments else due_on
    history = rate_history_between(due_on + timedelta(days=1), final_day)
    return PenaltyResult(
        tuple(segments),
        total,
        uncapped,
        selected.value,
        selected.valid_from,
        selected.document_number,
        cap_applied,
        cap,
        cap_day,
        (NO_CAP_WARNING,) if cap is None else (),
        history,
        sum(segment.days for segment in segments),
    )

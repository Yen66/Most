from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from construction_os.calc.acts import payment_deadline, signing_deadline
from construction_os.calc.penalty import (
    NO_CAP_WARNING,
    calculate_penalty,
    delay_days,
    penalty_for_segment,
    penalty_segments,
    rate_history_between,
)
from construction_os.money.core import money
from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.references.rates import RateNotFoundError, RateType, get_rate
from construction_os.storage.calendar import DbCalendar
from construction_os.storage.models import WorkCalendarRow

D = date.fromisoformat
M = Decimal


@pytest.mark.parametrize(
    "day,expected",
    [
        ("2024-10-28", "0.21"),
        ("2025-12-31", "0.16"),
        ("2026-02-15", "0.16"),
        ("2026-02-16", "0.155"),
        ("2026-03-22", "0.155"),
        ("2026-03-23", "0.15"),
        ("2026-04-26", "0.15"),
        ("2026-04-27", "0.145"),
        ("2026-06-21", "0.145"),
        ("2026-06-22", "0.1425"),
        ("2026-07-26", "0.1425"),
        ("2026-07-27", "0.14"),
        ("2026-08-01", "0.14"),
        ("2026-09-23", "0.14"),
    ],
)
def test_key_rate_boundaries(day, expected):
    assert get_rate(RateType.KEY_RATE, D(day)).value == M(expected)


def test_key_rate_before_catalog():
    with pytest.raises(RateNotFoundError):
        get_rate(RateType.KEY_RATE, D("2024-10-27"))


def test_P1_eis_deadlines_and_penalty(sqlite_session):
    sqlite_session.add_all(
        WorkCalendarRow(**row) for row in iter_calendar_days(2026)
    )
    sqlite_session.flush()
    cal = DbCalendar(sqlite_session).is_working
    signed = signing_deadline(D("2026-09-01"), cal)
    due = payment_deadline(signed, 7, cal)
    result = calculate_penalty(M("1000000"), due, as_of=D("2026-10-28"))
    assert signed == D("2026-09-29")
    assert due == D("2026-10-08")
    assert result.days == 20
    assert result.rate_used == M("0.14")
    assert result.total == M("9333.33")


def test_P2_treasury_deadline_and_penalty(sqlite_session):
    sqlite_session.add_all(
        WorkCalendarRow(**row) for row in iter_calendar_days(2026)
    )
    sqlite_session.flush()
    due = payment_deadline(
        D("2026-09-29"), 10, DbCalendar(sqlite_session).is_working
    )
    result = calculate_penalty(M("1000000"), due, as_of=D("2026-10-28"))
    assert due == D("2026-10-13")
    assert result.days == 15
    assert result.total == M("7000.00")


def test_P3_rate_on_payment_date_not_period_weighted():
    result = calculate_penalty(
        M("1000000"), D("2026-06-15"), as_of=D("2026-08-20"),
        paid_on=D("2026-08-15"), paid_amount=M("1000000"),
    )
    assert result.days == 61
    assert result.rate_used == M("0.14")
    assert result.total == M("28466.67")
    assert [r.rate for r in result.rate_history] == [
        M("0.145"), M("0.1425"), M("0.14")
    ]


def test_P4_cap_and_day_reached():
    result = calculate_penalty(
        M("1000000"), D("2026-01-05"), as_of=D("2026-07-24"),
        penalty_cap_pct=M("0.05"),
    )
    assert result.days == 200
    assert result.rate_used == M("0.1425")
    assert penalty_for_segment(M("1000000"), 1, M("0.1425")) == M("475.00")
    assert result.total_uncapped == M("95000.00")
    assert result.cap_value == M("50000.00")
    assert result.total == M("50000.00")
    assert result.cap_applied is True
    assert result.cap_reached_day == 106
    assert penalty_for_segment(M("1000000"), 105, M("0.1425")) == M("49875.00")
    assert penalty_for_segment(M("1000000"), 106, M("0.1425")) == M("50350.00")


def test_P5_partial_payment_segments():
    result = calculate_penalty(
        M("1000000"), D("2026-09-10"), as_of=D("2026-10-20"),
        paid_on=D("2026-09-30"), paid_amount=M("400000"),
    )
    assert result.days == 40
    assert [(s.debt, s.days, s.amount) for s in result.segments] == [
        (M("1000000"), 20, M("9333.33")),
        (M("600000"), 20, M("5600.00")),
    ]
    assert result.total == M("14933.33")
    assert result.days == delay_days(
        D("2026-09-10"), as_of=D("2026-10-20")
    )


def test_P6_no_delay_when_paid_on_due():
    result = calculate_penalty(
        M("1000000"), D("2026-09-10"), as_of=D("2026-09-20"),
        paid_on=D("2026-09-10"), paid_amount=M("1000000"),
    )
    assert result.days == 0
    assert result.total == M("0.00")
    assert result.segments == ()


@pytest.mark.parametrize(
    "days,expected",
    [(10, "34066.67"), (20, "68133.33")],
)
def test_P7_real_scale(days, expected):
    result = calculate_penalty(
        M("7300000"), D("2026-09-10"),
        as_of=D("2026-09-10") + timedelta(days=days),
    )
    assert result.days == days
    assert result.total == M(expected)


def test_E3_rounding_and_half_up():
    assert penalty_for_segment(M("1000000"), 20, M("0.14")) == M("9333.33")
    assert penalty_for_segment(M("7300000"), 10, M("0.14")) == M("34066.67")
    assert money(M("0.125")) == M("0.13")


def test_no_cap_exact_warning():
    result = calculate_penalty(
        M("1000000"), D("2026-10-08"), as_of=D("2026-10-28")
    )
    assert result.warnings == (NO_CAP_WARNING,)


def test_rate_date_override_changes_amount():
    normal = calculate_penalty(
        M("1000000"), D("2026-10-08"), as_of=D("2026-10-28")
    )
    override = calculate_penalty(
        M("1000000"), D("2026-10-08"), as_of=D("2026-10-28"),
        rate_date=D("2026-06-22"),
    )
    assert normal.total == M("9333.33")
    assert override.rate_used == M("0.1425")
    assert override.total == M("9500.00")


def test_rate_history_is_informational_only():
    history = rate_history_between(D("2026-06-16"), D("2026-08-15"))
    assert [r.rate for r in history] == [
        M("0.145"), M("0.1425"), M("0.14")
    ]
    assert history[0].start == D("2026-06-16")
    assert history[-1].end == D("2026-08-15")


def test_segments_additive_identity():
    due = D("2026-09-10")
    paid = D("2026-09-30")
    as_of = D("2026-10-20")
    segments = penalty_segments(
        M("1000000"), due, paid, M("400000"), as_of
    )
    assert sum(segment.days for segment in segments) == delay_days(
        due, as_of=as_of
    )


def test_no_penalty_accrual_table():
    from construction_os.storage.models import Base

    assert "penalty_accruals" not in Base.metadata.tables


@pytest.mark.parametrize(
    "day",
    [D("2026-01-12"), D("2026-02-17"), D("2026-03-16"),
     D("2026-05-01"), D("2026-07-01"), D("2026-09-01"),
     D("2026-10-01"), D("2026-11-01"), D("2026-12-01"),
     D("2027-01-11"), D("2027-02-19"), D("2027-03-15"),
     D("2027-04-15"), D("2027-06-01"), D("2027-07-01"),
     D("2027-08-01"), D("2027-09-01"), D("2027-10-01"),
     D("2027-11-01"), D("2027-05-15")],
)
def test_signing_deadline_identity_grid(sqlite_session, day):
    from construction_os.domain.calendar import add_working_days

    sqlite_session.add_all(
        WorkCalendarRow(**row)
        for year in (2026, 2027) for row in iter_calendar_days(year)
    )
    sqlite_session.flush()
    cal = DbCalendar(sqlite_session).is_working
    assert signing_deadline(day, cal) == add_working_days(day, 20, cal)


def test_payment_treasury_not_earlier_than_eis(sqlite_session):
    sqlite_session.add_all(
        WorkCalendarRow(**row) for row in iter_calendar_days(2026)
    )
    sqlite_session.flush()
    cal = DbCalendar(sqlite_session).is_working
    signed = D("2026-09-29")
    assert payment_deadline(signed, 10, cal) >= payment_deadline(
        signed, 7, cal
    )


def test_no_cap_min_identity():
    result = calculate_penalty(
        M("1000000"), D("2026-10-08"), as_of=D("2026-10-28")
    )
    assert result.total == result.total_uncapped

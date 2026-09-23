from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from construction_os.domain.calendar import (
    CalendarNotCoveredError,
    add_working_days,
    count_working_days,
    is_working_day,
)
from construction_os.references.calendar_seed import EXPECTED_MONTHS, iter_calendar_days
from construction_os.storage.calendar import DbCalendar
from construction_os.storage.models import WorkCalendarRow

D = date.fromisoformat


@pytest.fixture
def calendar(sqlite_session):
    for year in (2026, 2027):
        sqlite_session.add_all(WorkCalendarRow(**row) for row in iter_calendar_days(year))
    sqlite_session.flush()
    return DbCalendar(sqlite_session)


@pytest.mark.parametrize("year", [2026, 2027])
def test_seed_monthly_and_annual_totals(calendar, year):
    rows = calendar.session.scalars(
        select(WorkCalendarRow).where(
            func.extract("year", WorkCalendarRow.cal_date) == year
        )
    ).all()
    assert len(rows) == 365
    assert sum(row.is_working for row in rows) == 247
    assert sum(not row.is_working for row in rows) == 118
    assert tuple(
        sum(row.is_working for row in rows if row.cal_date.month == month)
        for month in range(1, 13)
    ) == EXPECTED_MONTHS[year]


@pytest.mark.parametrize(
    "day,working,kind",
    [
        ("2026-01-09", False, "transferred_day_off"),
        ("2026-12-31", False, "transferred_day_off"),
        ("2026-03-09", False, "transferred_day_off"),
        ("2026-05-11", False, "transferred_day_off"),
        ("2027-02-20", True, "transferred_working"),
        ("2027-02-22", False, "transferred_day_off"),
        ("2027-11-05", False, "transferred_day_off"),
        ("2027-12-31", False, "transferred_day_off"),
    ],
)
def test_special_dates(calendar, day, working, kind):
    row = calendar.day(D(day))
    assert row.is_working is working
    assert row.day_type == kind


@pytest.mark.parametrize(
    "year,expected",
    [
        (2026, {"2026-04-30", "2026-05-08", "2026-06-11", "2026-11-03"}),
        (2027, {"2027-02-20", "2027-04-30", "2027-06-11", "2027-11-03"}),
    ],
)
def test_shortened_days_exact(calendar, year, expected):
    rows = calendar.session.scalars(select(WorkCalendarRow)).all()
    assert {str(row.cal_date) for row in rows if row.cal_date.year == year and row.is_shortened} == expected


@pytest.mark.parametrize(
    "start,n,expected",
    [
        ("2026-01-01", 1, "2026-01-12"),
        ("2027-01-01", 1, "2027-01-11"),
        ("2026-09-01", 20, "2026-09-29"),
        ("2026-09-29", 7, "2026-10-08"),
        ("2026-09-29", 10, "2026-10-13"),
        ("2026-12-30", 3, "2027-01-13"),
        ("2027-02-19", 1, "2027-02-20"),
        ("2026-09-25", 20, "2026-10-23"),
    ],
)
def test_calendar_benchmarks(calendar, start, n, expected):
    assert add_working_days(D(start), n, calendar.is_working) == D(expected)


def test_count_2026(calendar):
    assert count_working_days(D("2026-01-01"), D("2026-12-31"), calendar.is_working) == 247


@pytest.mark.parametrize("day", ["2025-12-31", "2028-01-01"])
def test_calendar_out_of_coverage(calendar, day):
    with pytest.raises(CalendarNotCoveredError, match=f"calendar has no data for {day}"):
        is_working_day(D(day), calendar.is_working)


def test_count_rejects_uncovered_date(calendar):
    with pytest.raises(CalendarNotCoveredError, match="calendar has no data"):
        count_working_days(D("2027-12-30"), D("2028-01-01"), calendar.is_working)


def test_unsupported_seed_year():
    with pytest.raises(ValueError, match="calendar has no data"):
        iter_calendar_days(2028)


def test_calendar_no_tenant_column():
    assert "company_id" not in WorkCalendarRow.__table__.c


def test_calendar_no_mutable_dates(calendar):
    assert calendar.day(D("2027-02-20")).source == "ПП 1187 от 17.09.2026"

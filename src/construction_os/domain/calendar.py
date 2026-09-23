from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

WorkingLookup = Callable[[date], bool]


class CalendarNotCoveredError(LookupError):
    """The federal work calendar has no row for the requested date."""


def is_working_day(day: date, is_working: WorkingLookup) -> bool:
    value = is_working(day)
    if value is None:
        raise CalendarNotCoveredError(f"calendar has no data for {day}")
    return value


def add_working_days(start: date, n: int, is_working: WorkingLookup) -> date:
    """Return the n-th working day AFTER start; article 191 GK RF."""
    if n < 0:
        raise ValueError("working days cannot be negative")
    if n == 0:
        is_working_day(start, is_working)
        return start
    day = start
    counted = 0
    while counted < n:
        day += timedelta(days=1)
        if is_working_day(day, is_working):
            counted += 1
    return day


def count_working_days(start: date, end: date, is_working: WorkingLookup) -> int:
    """Count working days inclusively, rejecting every uncovered date."""
    if end < start:
        raise ValueError("end before start")
    result = 0
    day = start
    while day <= end:
        result += is_working_day(day, is_working)
        day += timedelta(days=1)
    return result

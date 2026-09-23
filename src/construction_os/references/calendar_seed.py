from __future__ import annotations

from datetime import date, timedelta
from uuid import NAMESPACE_URL, uuid5

EXPECTED_MONTHS = {
    2026: (15, 19, 21, 22, 19, 21, 23, 21, 22, 22, 20, 22),
    2027: (15, 19, 22, 22, 19, 21, 22, 22, 22, 21, 20, 22),
}
HOLIDAYS = {
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
    (2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4),
}
TRANSFERS_OFF = {
    2026: {
        (1, 9): "ПП 1466 от 24.09.2025",
        (3, 9): "ТК ст. 112 ч. 2 (автоперенос)",
        (5, 11): "ТК ст. 112 ч. 2 (автоперенос)",
        (12, 31): "ПП 1466 от 24.09.2025",
    },
    2027: {
        (2, 22): "ПП 1187 от 17.09.2026",
        (5, 3): "ТК ст. 112 ч. 2 (автоперенос)",
        (5, 10): "ТК ст. 112 ч. 2 (автоперенос)",
        (6, 14): "ТК ст. 112 ч. 2 (автоперенос)",
        (11, 5): "ПП 1187 от 17.09.2026",
        (12, 31): "ПП 1187 от 17.09.2026",
    },
}
TRANSFERS_WORKING = {2026: set(), 2027: {(2, 20)}}
SHORTENED = {
    2026: {(4, 30), (5, 8), (6, 11), (11, 3)},
    2027: {(2, 20), (4, 30), (6, 11), (11, 3)},
}


def iter_calendar_days(year: int) -> list[dict]:
    """Federal five-day work calendar; explicit PP 1466/1187 and TK 112 dates."""
    if year not in EXPECTED_MONTHS:
        raise ValueError(f"calendar has no data for year {year}")
    rows = []
    day = date(year, 1, 1)
    while day.year == year:
        key = (day.month, day.day)
        if key in TRANSFERS_WORKING[year]:
            kind, source = "transferred_working", (
                "ПП 1187 от 17.09.2026"
            )
        elif key in HOLIDAYS:
            kind, source = "holiday", "ТК ст. 112"
        elif key in TRANSFERS_OFF[year]:
            kind, source = "transferred_day_off", TRANSFERS_OFF[year][key]
        elif day.weekday() >= 5:
            kind, source = "weekend", "пятидневная неделя"
        else:
            kind, source = "working", "пятидневная неделя"
        working = kind in {"working", "transferred_working"}
        rows.append(
            {
                "id": uuid5(NAMESPACE_URL, f"construction_os/work_calendar/{day.isoformat()}"),
                "cal_date": day,
                "is_working": working,
                "day_type": kind,
                "is_shortened": key in SHORTENED[year] and working,
                "source": source,
            }
        )
        day += timedelta(days=1)
    monthly = tuple(
        sum(row["is_working"] for row in rows if row["cal_date"].month == month)
        for month in range(1, 13)
    )
    if monthly != EXPECTED_MONTHS[year] or len(rows) != 365 or sum(
        row["is_working"] for row in rows
    ) != 247:
        raise ValueError(f"calendar {year} control totals mismatch: {monthly}")
    return rows

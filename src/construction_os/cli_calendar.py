from __future__ import annotations

import argparse
from datetime import date, timedelta

from construction_os.domain.calendar import (
    CalendarNotCoveredError,
    add_working_days,
    count_working_days,
)
from construction_os.storage.calendar import DbCalendar


def configure_calendar(sub) -> None:
    calendar = sub.add_parser("calendar")
    actions = calendar.add_subparsers(dest="calendar_command", required=True)
    check = actions.add_parser("check")
    check.add_argument("--date", type=date.fromisoformat, required=True)
    add = actions.add_parser("add")
    add.add_argument("--date", type=date.fromisoformat, required=True)
    add.add_argument("--working-days", type=int, required=True)
    count = actions.add_parser("count")
    count.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    count.add_argument("--to", dest="end", type=date.fromisoformat, required=True)


def run_calendar(args: argparse.Namespace, session) -> int:
    calendar = DbCalendar(session)
    try:
        if args.calendar_command == "check":
            row = calendar.day(args.date)
            print(
                f"{row.cal_date}: {'рабочий' if row.is_working else 'нерабочий'}; "
                f"day_type={row.day_type}; is_shortened={row.is_shortened}; source={row.source}"
            )
        elif args.calendar_command == "add":
            result = add_working_days(args.date, args.working_days, calendar.is_working)
            print(f"Результат: {result}")
            day = args.date
            while day < result:
                day += timedelta(days=1)
                if calendar.is_working(day):
                    print(f"  рабочий: {day}")
        else:
            result = count_working_days(args.start, args.end, calendar.is_working)
            print(f"Рабочих дней: {result}")
    except (CalendarNotCoveredError, ValueError) as error:
        print(f"нет данных: {error}")
        return 2
    return 0

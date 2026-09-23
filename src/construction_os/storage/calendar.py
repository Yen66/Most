from __future__ import annotations

from datetime import date

from sqlalchemy import select

from construction_os.domain.calendar import CalendarNotCoveredError
from construction_os.storage.models import WorkCalendarRow


class DbCalendar:
    def __init__(self, session):
        self.session = session

    def day(self, day: date) -> WorkCalendarRow:
        row = self.session.scalar(select(WorkCalendarRow).where(WorkCalendarRow.cal_date == day))
        if row is None:
            raise CalendarNotCoveredError(f"calendar has no data for {day}")
        return row

    def is_working(self, day: date) -> bool:
        return self.day(day).is_working

"""Return deterministic registrar-open fixture dates for existing workflow tests."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from app.storage import now


def open_day(days: int = 2, *, base: date | None = None) -> date:
    day = (base if base is not None else now().date()) + timedelta(days=days)
    while day.weekday() >= 4:  # Friday, Saturday, Sunday are closed.
        day += timedelta(days=1)
    return day


def open_time(days: int = 2, hour: int = 15, minute: int = 0) -> datetime:
    return datetime.combine(open_day(days), time(hour, minute), tzinfo=ZoneInfo('Asia/Manila'))

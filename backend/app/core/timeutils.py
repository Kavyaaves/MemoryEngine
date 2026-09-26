"""Time helpers.

Chat exports contain *naive* local times ("21:15", no timezone). The database stores
timezone-aware timestamps. Anything the user sees or types as a date — date filters,
"messages from June", timeline buckets — is interpreted in the user's timezone
(DEFAULT_TIMEZONE, e.g. Asia/Kolkata), never in the server's.
"""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, literal_column

from app.config import get_settings

PERIOD_FORMATS = {"year": "YYYY", "month": "YYYY-MM", "day": "YYYY-MM-DD"}
TIMEZONE_NAME = re.compile(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+)*")  # e.g. Asia/Kolkata — safe to inline in SQL


def user_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().default_timezone)


def make_aware(ts: datetime | None) -> datetime | None:
    """Attach the user's timezone to a naive timestamp. Aware timestamps are returned unchanged."""
    if ts is None or ts.tzinfo is not None:
        return ts
    return ts.replace(tzinfo=user_timezone())


def start_of_day(day: date | str | None) -> datetime | None:
    """Midnight at the start of `day` in the user's timezone. Accepts a date or 'YYYY-MM-DD'."""
    if day is None:
        return None
    if isinstance(day, str):
        try:
            day = date.fromisoformat(day[:10])
        except ValueError:
            return None
    return datetime(day.year, day.month, day.day, tzinfo=user_timezone())


def end_of_day(day: date | str | None) -> datetime | None:
    """Midnight at the END of `day`, i.e. an exclusive upper bound that includes the whole day."""
    start = start_of_day(day)
    return start + timedelta(days=1) if start else None


def local_period(column, granularity: str):
    """SQL expression bucketing a timestamp column into 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD'
    using the user's local calendar (so a message at 01:00 IST lands on the right day).

    The constants are written into the SQL rather than sent as parameters: otherwise the
    SELECT and the GROUP BY get different placeholders ($1 vs $3) and PostgreSQL refuses
    to treat them as the same expression.
    """
    timezone_name = get_settings().default_timezone
    if not TIMEZONE_NAME.fullmatch(timezone_name) or granularity not in PERIOD_FORMATS:
        raise ValueError("invalid timezone or granularity")
    local_time = func.timezone(literal_column(f"'{timezone_name}'"), column)
    truncated = func.date_trunc(literal_column(f"'{granularity}'"), local_time)
    return func.to_char(truncated, literal_column(f"'{PERIOD_FORMATS[granularity]}'"))

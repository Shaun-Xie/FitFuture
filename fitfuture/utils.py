from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        return None


def parse_optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def parse_workout_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return None


def get_week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())

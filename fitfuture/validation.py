from __future__ import annotations

from datetime import datetime
from typing import Any

from .utils import parse_optional_float, parse_optional_int, parse_optional_text

ALLOWED_SOURCES = {"", "manual", "app", "device"}
ALLOWED_GENDERS = {"", "M", "F"}


def is_valid_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return False

    return True


def is_valid_time(value: str | None) -> bool:
    if not value:
        return True

    try:
        datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        return False

    return True


def validate_workout_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    values = {
        "workout_date": parse_optional_text(form.get("workout_date")),
        "start_time": parse_optional_text(form.get("start_time")),
        "end_time": parse_optional_text(form.get("end_time")),
        "total_duration_minutes": parse_optional_int(form.get("total_duration_minutes")),
        "perceived_intensity": parse_optional_int(form.get("perceived_intensity")),
        "recovery_rating": parse_optional_int(form.get("recovery_rating")),
        "sleep_hours": parse_optional_float(form.get("sleep_hours")),
        "source": parse_optional_text(form.get("source")) or "",
        "notes": parse_optional_text(form.get("notes")),
    }
    errors: list[str] = []

    if not values["workout_date"]:
        errors.append("Workout date is required.")
    elif not is_valid_date(values["workout_date"]):
        errors.append("Workout date must be a valid date.")

    if not is_valid_time(values["start_time"]):
        errors.append("Start time must be valid.")
    if not is_valid_time(values["end_time"]):
        errors.append("End time must be valid.")

    duration = values["total_duration_minutes"]
    if duration is not None and not 1 <= duration <= 600:
        errors.append("Duration must be between 1 and 600 minutes.")

    intensity = values["perceived_intensity"]
    if intensity is not None and not 1 <= intensity <= 10:
        errors.append("Effort must be between 1 and 10.")

    recovery = values["recovery_rating"]
    if recovery is not None and not 1 <= recovery <= 5:
        errors.append("Recovery must be between 1 and 5.")

    sleep_hours = values["sleep_hours"]
    if sleep_hours is not None and not 0 <= sleep_hours <= 16:
        errors.append("Sleep must be between 0 and 16 hours.")

    if values["source"] not in ALLOWED_SOURCES:
        errors.append("Source must be manual, app, device, or blank.")

    if values["notes"] and len(values["notes"]) > 500:
        errors.append("Notes must stay under 500 characters.")

    return values, errors


def validate_profile_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    gender = (parse_optional_text(form.get("gender")) or "").upper()
    values = {
        "age": parse_optional_int(form.get("age")),
        "gender": gender,
    }
    errors: list[str] = []

    if values["age"] is not None and not 10 <= values["age"] <= 90:
        errors.append("Age must be between 10 and 90.")

    if values["gender"] not in ALLOWED_GENDERS:
        errors.append("Gender must be male, female, or not set.")

    return values, errors


def validate_auth_form(form: Any, *, require_password_length: bool) -> tuple[dict[str, str], list[str]]:
    values = {
        "email": form.get("email", "").strip().lower(),
        "password": form.get("password", ""),
    }
    errors: list[str] = []

    if not values["email"]:
        errors.append("Email is required.")
    elif "@" not in values["email"] or "." not in values["email"].split("@")[-1]:
        errors.append("Enter a valid email address.")

    if not values["password"]:
        errors.append("Password is required.")
    elif require_password_length and len(values["password"]) < 8:
        errors.append("Password must be at least 8 characters.")

    return values, errors


def validate_goals_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    values = {
        "weekly_minutes_goal": parse_optional_int(form.get("weekly_minutes_goal")),
        "weekly_sessions_goal": parse_optional_int(form.get("weekly_sessions_goal")),
    }
    errors: list[str] = []

    if values["weekly_minutes_goal"] is None:
        errors.append("Weekly minutes goal is required.")
    elif not 30 <= values["weekly_minutes_goal"] <= 600:
        errors.append("Weekly minutes goal must be between 30 and 600.")

    if values["weekly_sessions_goal"] is None:
        errors.append("Weekly sessions goal is required.")
    elif not 1 <= values["weekly_sessions_goal"] <= 14:
        errors.append("Weekly sessions goal must be between 1 and 14.")

    return values, errors

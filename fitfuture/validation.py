from __future__ import annotations

from datetime import datetime
from typing import Any

from .blocks import ALLOWED_TRAINING_FOCUSES
from .utils import parse_optional_float, parse_optional_int, parse_optional_text
from .utils import parse_workout_date

ALLOWED_SOURCES = {"", "manual", "app", "device"}
ALLOWED_GENDERS = {"", "M", "F"}


def has_submitted_value(form: Any, key: str) -> bool:
    value = form.get(key)
    return value is not None and str(value).strip() != ""


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
        "total_duration_minutes": parse_optional_int(
            form.get("total_duration_minutes")
        ),
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
        errors.append("Intensity must be between 1 and 10.")

    recovery = values["recovery_rating"]
    if recovery is None and has_submitted_value(form, "recovery_rating"):
        errors.append("Recovery must be a whole number.")
    elif recovery is not None and not 1 <= recovery <= 10:
        errors.append("Recovery must be between 1 and 10.")

    sleep_hours = values["sleep_hours"]
    if sleep_hours is not None and not 0 <= sleep_hours <= 16:
        errors.append("Sleep must be between 0 and 16 hours.")

    if values["source"] not in ALLOWED_SOURCES:
        errors.append("Source must be manual, app, device, or blank.")

    if values["notes"] and len(values["notes"]) > 500:
        errors.append("Notes must stay under 500 characters.")

    return values, errors


def validate_sleep_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    values = {
        "sleep_date": parse_optional_text(form.get("sleep_date")),
        "sleep_hours": parse_optional_float(form.get("sleep_hours")),
        "recovery_rating": parse_optional_int(form.get("recovery_rating")),
        "notes": parse_optional_text(form.get("notes")),
    }
    errors: list[str] = []

    if not values["sleep_date"]:
        errors.append("Sleep date is required.")
    elif not is_valid_date(values["sleep_date"]):
        errors.append("Sleep date must be a valid date.")

    sleep_hours = values["sleep_hours"]
    if sleep_hours is None:
        errors.append("Sleep hours are required.")
    elif not 0 <= sleep_hours <= 16:
        errors.append("Sleep must be between 0 and 16 hours.")

    recovery = values["recovery_rating"]
    if recovery is None and has_submitted_value(form, "recovery_rating"):
        errors.append("Recovery must be a whole number.")
    elif recovery is not None and not 1 <= recovery <= 10:
        errors.append("Recovery must be between 1 and 10.")

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


def validate_auth_form(
    form: Any, *, require_password_length: bool
) -> tuple[dict[str, str], list[str]]:
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
    workouts_per_week = parse_optional_int(form.get("workouts_per_week"))
    workout_duration = parse_optional_int(form.get("workout_duration_minutes"))
    values = {
        "workouts_per_week": workouts_per_week,
        "workout_duration_minutes": workout_duration,
        "weekly_sessions_goal": (
            workouts_per_week
            if workouts_per_week is not None
            else parse_optional_int(form.get("weekly_sessions_goal"))
        ),
        "weekly_minutes_goal": (
            (workouts_per_week * workout_duration)
            if workouts_per_week is not None and workout_duration is not None
            else parse_optional_int(form.get("weekly_minutes_goal"))
        ),
    }
    errors: list[str] = []

    if values["weekly_sessions_goal"] is None:
        errors.append("Workouts per week goal is required.")
    elif not 1 <= values["weekly_sessions_goal"] <= 14:
        errors.append("Workouts per week goal must be between 1 and 14.")

    if workout_duration is None and form.get("workout_duration_minutes") is not None:
        errors.append("Duration each workout is required.")
    elif workout_duration is not None and not 10 <= workout_duration <= 300:
        errors.append("Duration each workout must be between 10 and 300 minutes.")

    if values["weekly_minutes_goal"] is None:
        errors.append("Total weekly minutes goal is required.")
    elif not 30 <= values["weekly_minutes_goal"] <= 900:
        errors.append("Total weekly minutes goal must be between 30 and 900.")

    return values, errors


def validate_training_block_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    training_focus = (parse_optional_text(form.get("training_focus")) or "").lower()
    values = {
        "block_name": parse_optional_text(form.get("block_name")),
        "training_focus": training_focus,
        "start_date": parse_optional_text(form.get("start_date")),
        "end_date": parse_optional_text(form.get("end_date")),
        "workouts_per_week": parse_optional_int(form.get("workouts_per_week")),
        "workout_duration_minutes": parse_optional_int(
            form.get("workout_duration_minutes")
        ),
        "target_weekly_minutes": (
            parse_optional_int(form.get("workouts_per_week"))
            * parse_optional_int(form.get("workout_duration_minutes"))
            if parse_optional_int(form.get("workouts_per_week")) is not None
            and parse_optional_int(form.get("workout_duration_minutes")) is not None
            else parse_optional_int(form.get("target_weekly_minutes"))
        ),
        "target_weekly_sessions": (
            parse_optional_int(form.get("workouts_per_week"))
            if parse_optional_int(form.get("workouts_per_week")) is not None
            else parse_optional_int(form.get("target_weekly_sessions"))
        ),
        "target_effort": parse_optional_int(form.get("target_effort")),
        "notes": parse_optional_text(form.get("notes")),
    }
    errors: list[str] = []

    if not values["block_name"]:
        errors.append("Block name is required.")
    elif len(values["block_name"]) > 60:
        errors.append("Block name must stay under 60 characters.")

    if values["training_focus"] not in ALLOWED_TRAINING_FOCUSES:
        errors.append("Training focus must be one of the available options.")

    start_date = parse_workout_date(values["start_date"])
    end_date = parse_workout_date(values["end_date"])
    if not values["start_date"]:
        errors.append("Block start date is required.")
    elif start_date is None:
        errors.append("Block start date must be valid.")

    if not values["end_date"]:
        errors.append("Block end date is required.")
    elif end_date is None:
        errors.append("Block end date must be valid.")

    if start_date and end_date:
        duration_days = (end_date - start_date).days + 1
        if duration_days <= 0:
            errors.append("Block end date must be on or after the start date.")
        elif duration_days > 183:
            errors.append("Training blocks must be 26 weeks or shorter.")

    if values["target_weekly_minutes"] is None:
        errors.append("Total weekly minutes target is required.")
    elif not 30 <= values["target_weekly_minutes"] <= 900:
        errors.append("Total weekly minutes target must be between 30 and 900.")

    if values["target_weekly_sessions"] is None:
        errors.append("Workouts per week target is required.")
    elif not 1 <= values["target_weekly_sessions"] <= 14:
        errors.append("Workouts per week target must be between 1 and 14.")

    if (
        values["workout_duration_minutes"] is None
        and form.get("workout_duration_minutes") is not None
    ):
        errors.append("Duration each workout target is required.")
    elif (
        values["workout_duration_minutes"] is not None
        and not 10 <= values["workout_duration_minutes"] <= 300
    ):
        errors.append(
            "Duration each workout target must be between 10 and 300 minutes."
        )

    if values["target_effort"] is not None and not 1 <= values["target_effort"] <= 10:
        errors.append("Block target effort must be between 1 and 10.")

    if values["notes"] and len(values["notes"]) > 300:
        errors.append("Block notes must stay under 300 characters.")

    return values, errors

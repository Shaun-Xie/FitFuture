from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .auth import get_current_user_id, login_required
from .db import fetch_all, fetch_one, get_db
from .goals import get_user_goals, save_user_goals
from .users import get_user_profile
from .utils import parse_optional_int, parse_optional_text
from .validation import validate_goals_form, validate_profile_form, validate_workout_form

workouts_bp = Blueprint("workouts", __name__)


def get_workout_filters() -> dict[str, str]:
    return {
        "min_date": request.args.get("min_date", "").strip(),
        "max_date": request.args.get("max_date", "").strip(),
        "min_intensity": request.args.get("min_intensity", "").strip(),
    }


def fetch_workouts(
    user_id: int,
    filters: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM workout_sessions WHERE user_id = ?"
    params: list[Any] = [user_id]

    if filters:
        if filters["min_date"]:
            query += " AND workout_date >= ?"
            params.append(filters["min_date"])

        if filters["max_date"]:
            query += " AND workout_date <= ?"
            params.append(filters["max_date"])

        min_intensity = parse_optional_int(filters["min_intensity"])
        if min_intensity is not None:
            query += " AND perceived_intensity >= ?"
            params.append(min_intensity)

    query += " ORDER BY workout_date DESC, workout_id DESC"
    return fetch_all(query, params)


def build_workout_metrics(
    workouts: list[dict[str, Any]],
    filters: dict[str, str],
) -> dict[str, Any]:
    durations = [
        workout["total_duration_minutes"]
        for workout in workouts
        if workout.get("total_duration_minutes") is not None
    ]
    intensities = [
        workout["perceived_intensity"]
        for workout in workouts
        if workout.get("perceived_intensity") is not None
    ]

    return {
        "session_count": len(workouts),
        "total_minutes": sum(durations),
        "avg_duration": sum(durations) / len(durations) if durations else None,
        "avg_intensity": sum(intensities) / len(intensities) if intensities else None,
        "latest_date": workouts[0]["workout_date"] if workouts else None,
        "active_filter_count": sum(1 for value in filters.values() if value),
    }


def fetch_workout(workout_id: int, user_id: int) -> dict[str, Any] | None:
    return fetch_one(
        "SELECT * FROM workout_sessions WHERE workout_id = ? AND user_id = ?",
        (workout_id, user_id),
    )


def build_workout_values(form: Any, user_id: int) -> tuple[Any, ...]:
    return (
        user_id,
        form["workout_date"],
        parse_optional_text(form.get("start_time")),
        parse_optional_text(form.get("end_time")),
        parse_optional_int(form.get("total_duration_minutes")),
        parse_optional_int(form.get("perceived_intensity")),
        parse_optional_text(form.get("source")),
        parse_optional_text(form.get("notes")),
    )


def render_workouts_page(
    workout: dict[str, Any] | None = None,
    workout_form: dict[str, Any] | None = None,
    workout_errors: list[str] | None = None,
    profile_form: dict[str, Any] | None = None,
    profile_errors: list[str] | None = None,
    goal_form: dict[str, Any] | None = None,
    goal_errors: list[str] | None = None,
) -> str:
    user_id = get_current_user_id()
    filters = get_workout_filters()
    workouts = fetch_workouts(user_id, filters)
    profile = get_user_profile(user_id)
    goals = get_user_goals(user_id)

    return render_template(
        "workouts.html",
        active_view="workouts",
        filters=filters,
        workouts=workouts,
        workout_metrics=build_workout_metrics(workouts, filters),
        workout=workout,
        workout_form=workout_form or workout or {},
        workout_errors=workout_errors or [],
        profile_form=profile_form or profile or {},
        profile_errors=profile_errors or [],
        goal_form=goal_form or goals,
        goal_errors=goal_errors or [],
        form_action=(
            url_for("workouts.create_workout")
            if workout is None
            else url_for("workouts.update_workout", workout_id=workout["workout_id"])
        ),
        profile=profile,
        goals=goals,
    )


@workouts_bp.route("/")
@login_required
def index() -> str:
    return render_workouts_page()


@workouts_bp.route("/workouts", methods=["POST"])
@login_required
def create_workout() -> Any:
    user_id = get_current_user_id()
    values, errors = validate_workout_form(request.form)
    if errors:
        return (
            render_workouts_page(
                workout_form=values,
                workout_errors=errors,
            ),
            400,
        )

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO workout_sessions
            (user_id, workout_date, start_time, end_time,
             total_duration_minutes, perceived_intensity, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            build_workout_values(values, user_id),
        )

    flash("Workout logged.", "success")
    return redirect(url_for("workouts.index"))


@workouts_bp.route("/workouts/<int:workout_id>/edit")
@login_required
def edit_workout(workout_id: int) -> str:
    workout = fetch_workout(workout_id, get_current_user_id())
    if workout is None:
        abort(404)

    return render_workouts_page(workout)


@workouts_bp.route("/workouts/<int:workout_id>", methods=["POST"])
@login_required
def update_workout(workout_id: int) -> Any:
    user_id = get_current_user_id()
    workout = fetch_workout(workout_id, user_id)
    if workout is None:
        abort(404)

    values, errors = validate_workout_form(request.form)
    if errors:
        return (
            render_workouts_page(
                workout=workout,
                workout_form=values,
                workout_errors=errors,
            ),
            400,
        )

    with get_db() as conn:
        conn.execute(
            """
            UPDATE workout_sessions
            SET user_id = ?, workout_date = ?, start_time = ?, end_time = ?,
                total_duration_minutes = ?, perceived_intensity = ?,
                source = ?, notes = ?
            WHERE workout_id = ? AND user_id = ?
            """,
            build_workout_values(values, user_id) + (workout_id, user_id),
        )

    flash("Workout updated.", "success")
    return redirect(url_for("workouts.index"))


@workouts_bp.route("/workouts/<int:workout_id>/delete", methods=["POST"])
@login_required
def delete_workout(workout_id: int) -> Any:
    user_id = get_current_user_id()
    with get_db() as conn:
        conn.execute(
            "DELETE FROM workout_sessions WHERE workout_id = ? AND user_id = ?",
            (workout_id, user_id),
        )

    flash("Workout deleted.", "success")
    return redirect(url_for("workouts.index"))


@workouts_bp.route("/profile", methods=["POST"])
@login_required
def update_profile() -> Any:
    user_id = get_current_user_id()
    values, errors = validate_profile_form(request.form)
    if errors:
        return (
            render_workouts_page(
                profile_form=values,
                profile_errors=errors,
            ),
            400,
        )

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO user_profiles (user_id, age, gender)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                age = excluded.age,
                gender = excluded.gender
            """,
            (
                user_id,
                values["age"],
                values["gender"] or None,
            ),
        )

    flash("Profile saved.", "success")
    return redirect(url_for("workouts.index"))


@workouts_bp.route("/goals", methods=["POST"])
@login_required
def update_goals() -> Any:
    user_id = get_current_user_id()
    values, errors = validate_goals_form(request.form)
    if errors:
        return (
            render_workouts_page(
                goal_form=values,
                goal_errors=errors,
            ),
            400,
        )

    save_user_goals(
        user_id,
        values["weekly_minutes_goal"],
        values["weekly_sessions_goal"],
    )

    flash("Training goals saved.", "success")
    return redirect(url_for("workouts.index"))

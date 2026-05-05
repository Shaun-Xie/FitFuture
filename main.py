from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from flask import Flask, abort, redirect, render_template, request, url_for

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "fitfuture.db"
DEFAULT_USER_ID = 1
ANALYTICS_WINDOW_DAYS = 30

DATASET_CONFIG = (
    {
        "filename": "gym_members_exercise_tracking.csv",
        "key": "gym",
        "label": "Gym Members Exercise Tracking",
        "usecols": ["Age", "Gender", "Session_Duration (hours)"],
        "metrics": {
            "Session_Duration (hours)": "avg_session_hours",
        },
    },
    {
        "filename": "health_fitness_tracking_365days.csv",
        "key": "hf365",
        "label": "Health Fitness Tracking 365 Days",
        "usecols": ["age", "gender", "steps", "exercise_minutes"],
        "metrics": {
            "steps": "avg_steps",
            "exercise_minutes": "avg_exercise_minutes",
        },
    },
    {
        "filename": "health_fitness_dataset.csv",
        "key": "health",
        "label": "General Health + Wellness Dataset",
        "usecols": ["daily_steps", "hours_sleep", "resting_heart_rate"],
        "metrics": {
            "daily_steps": "avg_steps",
            "hours_sleep": "avg_sleep_hours",
            "resting_heart_rate": "avg_resting_hr",
        },
    },
)

EXTERNAL_STATS: dict[str, dict[str, Any]] = {}
DATAFRAMES: dict[str, pd.DataFrame] = {}


# ===========================================================
# DATABASE HELPERS
# ===========================================================

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def fetch_all(
    query: str,
    params: list[Any] | tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def ensure_default_user(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM users")
    if cursor.fetchone()["c"] == 0:
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, created_at, status)
            VALUES (?, ?, ?, ?)
            """,
            ("test@example.com", "hash", datetime.utcnow().isoformat(), "ACTIVE"),
        )


def ensure_default_profile(
    cursor: sqlite3.Cursor,
    user_id: int = DEFAULT_USER_ID,
) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM user_profiles WHERE user_id = ?", (user_id,))
    if cursor.fetchone()["c"] == 0:
        cursor.execute(
            """
            INSERT INTO user_profiles (user_id, age, gender)
            VALUES (?, ?, ?)
            """,
            (user_id, 22, "M"),
        )


def init_db() -> None:
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE'
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                age INTEGER,
                gender TEXT,
                height_cm REAL,
                weight_kg REAL,
                bmi REAL,
                resting_heart_rate REAL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workout_sessions (
                workout_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workout_date TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                total_duration_minutes INTEGER,
                perceived_intensity INTEGER,
                source TEXT,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            """
        )

        ensure_default_user(cur)
        ensure_default_profile(cur)


# ===========================================================
# DATASET HELPERS
# ===========================================================

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


def add_mean_metrics(
    entry: dict[str, Any],
    df: pd.DataFrame,
    metrics: dict[str, str],
) -> None:
    for column_name, metric_name in metrics.items():
        if column_name in df.columns:
            entry[metric_name] = df[column_name].mean()


def compute_external_stats() -> dict[str, dict[str, Any]]:
    global EXTERNAL_STATS, DATAFRAMES

    if EXTERNAL_STATS:
        return EXTERNAL_STATS

    stats: dict[str, dict[str, Any]] = {}

    for dataset in DATASET_CONFIG:
        path = BASE_DIR / dataset["filename"]
        entry: dict[str, Any] = {"name": dataset["label"], "exists": False}

        if not path.exists():
            stats[dataset["key"]] = entry
            continue

        try:
            df = pd.read_csv(path, usecols=dataset["usecols"])
            header = pd.read_csv(path, nrows=0)

            DATAFRAMES[dataset["key"]] = df
            entry["exists"] = True
            entry["num_rows"] = len(df)
            entry["num_cols"] = len(header.columns)

            add_mean_metrics(entry, df, dataset["metrics"])
        except Exception as exc:
            entry["error"] = str(exc)

        stats[dataset["key"]] = entry

    EXTERNAL_STATS = stats
    return stats


# ===========================================================
# ANALYTICS HELPERS
# ===========================================================

def get_user_profile(user_id: int = DEFAULT_USER_ID) -> dict[str, Any] | None:
    return fetch_one("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))


def percentile_rank(series: pd.Series, value: float) -> float | None:
    cleaned_values = [float(item) for item in series if pd.notnull(item)]
    if not cleaned_values:
        return None

    count = sum(1 for item in cleaned_values if item <= value)
    return 100 * count / len(cleaned_values)


def compute_fitness_summary(user_id: int = DEFAULT_USER_ID) -> dict[str, Any]:
    profile = get_user_profile(user_id) or {}
    result: dict[str, Any] = {"has_data": False}

    window_start = (date.today() - timedelta(days=ANALYTICS_WINDOW_DAYS)).isoformat()
    rows = fetch_all(
        """
        SELECT workout_date, total_duration_minutes
        FROM workout_sessions
        WHERE user_id = ? AND workout_date >= ? AND total_duration_minutes IS NOT NULL
        """,
        (user_id, window_start),
    )

    if rows:
        durations = [row["total_duration_minutes"] for row in rows]
        total_minutes = sum(durations)
        average_duration = total_minutes / len(durations)

        workout_dates = [datetime.fromisoformat(row["workout_date"]).date() for row in rows]
        tracked_span_days = max((max(workout_dates) - min(workout_dates)).days + 1, 1)

        weekly_minutes = total_minutes * 7 / tracked_span_days
        current_score = min(10, weekly_minutes / 30)
        projected_score = min(10, current_score + 1)

        result.update(
            has_data=True,
            total_minutes_30d=total_minutes,
            avg_duration=average_duration,
            weekly_minutes=weekly_minutes,
            current_score=current_score,
            projected_score=projected_score,
        )

    compute_external_stats()

    age = parse_optional_int(profile.get("age"))
    gender = parse_optional_text(profile.get("gender"))
    gender = gender.upper() if gender else None

    if age and gender and result.get("weekly_minutes"):
        result["cohort_label"] = f"{age - 2}-{age + 2}yo {'males' if gender == 'M' else 'females'}"

        df365 = DATAFRAMES.get("hf365")
        if df365 is not None and {"age", "gender", "exercise_minutes"}.issubset(df365.columns):
            cohort = df365[
                (df365["age"].between(age - 2, age + 2))
                & (df365["gender"].astype(str).str[0].str.upper() == gender)
            ]
            if not cohort.empty:
                daily_equivalent = result["weekly_minutes"] / 7
                result["hf365_percentile"] = percentile_rank(
                    cohort["exercise_minutes"],
                    daily_equivalent,
                )

        df_gym = DATAFRAMES.get("gym")
        if df_gym is not None and {"Age", "Gender", "Session_Duration (hours)"}.issubset(df_gym.columns):
            cohort = df_gym[
                (df_gym["Age"].between(age - 2, age + 2))
                & (df_gym["Gender"].astype(str).str[0].str.upper() == gender)
            ]
            if not cohort.empty and result.get("avg_duration"):
                session_minutes = cohort["Session_Duration (hours)"] * 60
                result["gym_percentile"] = percentile_rank(
                    session_minutes,
                    result["avg_duration"],
                )

    return result


def build_chart_data(
    external_stats: dict[str, dict[str, Any]],
    fitness_summary: dict[str, Any],
) -> dict[str, float | None]:
    chart_data: dict[str, float | None] = {
        "user_daily_exercise": None,
        "pop_daily_exercise": None,
        "user_avg_duration": None,
        "pop_avg_duration": None,
        "current_score": None,
        "projected_score": None,
    }

    if fitness_summary.get("has_data"):
        chart_data["user_daily_exercise"] = fitness_summary["weekly_minutes"] / 7
        chart_data["user_avg_duration"] = fitness_summary["avg_duration"]
        chart_data["current_score"] = fitness_summary["current_score"]
        chart_data["projected_score"] = fitness_summary["projected_score"]

    if external_stats.get("hf365", {}).get("avg_exercise_minutes") is not None:
        chart_data["pop_daily_exercise"] = external_stats["hf365"]["avg_exercise_minutes"]

    if external_stats.get("gym", {}).get("avg_session_hours") is not None:
        chart_data["pop_avg_duration"] = external_stats["gym"]["avg_session_hours"] * 60

    return chart_data


# ===========================================================
# WORKOUT HELPERS
# ===========================================================

def get_workout_filters() -> dict[str, str]:
    return {
        "min_date": request.args.get("min_date", "").strip(),
        "max_date": request.args.get("max_date", "").strip(),
        "min_intensity": request.args.get("min_intensity", "").strip(),
    }


def fetch_workouts(filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM workout_sessions WHERE 1=1"
    params: list[Any] = []

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


def fetch_workout(workout_id: int) -> dict[str, Any] | None:
    return fetch_one("SELECT * FROM workout_sessions WHERE workout_id = ?", (workout_id,))


def build_workout_values(form: Any) -> tuple[Any, ...]:
    return (
        int(form["user_id"]),
        form["workout_date"],
        parse_optional_text(form.get("start_time")),
        parse_optional_text(form.get("end_time")),
        parse_optional_int(form.get("total_duration_minutes")),
        parse_optional_int(form.get("perceived_intensity")),
        parse_optional_text(form.get("source")),
        parse_optional_text(form.get("notes")),
    )


def render_workouts_page(workout: dict[str, Any] | None = None) -> str:
    filters = get_workout_filters()

    return render_template(
        "workouts.html",
        active_view="workouts",
        filters=filters,
        workouts=fetch_workouts(filters),
        workout=workout,
        form_action=(
            url_for("create_workout")
            if workout is None
            else url_for("update_workout", workout_id=workout["workout_id"])
        ),
        profile=get_user_profile(DEFAULT_USER_ID),
    )


init_db()


# ===========================================================
# ROUTES
# ===========================================================

@app.route("/")
def index() -> str:
    return render_workouts_page()


@app.route("/analytics")
def analytics() -> str:
    external_stats = compute_external_stats()
    fitness_summary = compute_fitness_summary(DEFAULT_USER_ID)

    return render_template(
        "analytics.html",
        active_view="analytics",
        external_stats=external_stats,
        fitness_summary=fitness_summary,
        chart_data=build_chart_data(external_stats, fitness_summary),
    )


@app.route("/workouts", methods=["POST"])
def create_workout() -> Any:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO workout_sessions
            (user_id, workout_date, start_time, end_time,
             total_duration_minutes, perceived_intensity, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            build_workout_values(request.form),
        )

    return redirect(url_for("index"))


@app.route("/workouts/<int:workout_id>/edit")
def edit_workout(workout_id: int) -> str:
    workout = fetch_workout(workout_id)
    if workout is None:
        abort(404)

    return render_workouts_page(workout)


@app.route("/workouts/<int:workout_id>", methods=["POST"])
def update_workout(workout_id: int) -> Any:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE workout_sessions
            SET user_id = ?, workout_date = ?, start_time = ?, end_time = ?,
                total_duration_minutes = ?, perceived_intensity = ?,
                source = ?, notes = ?
            WHERE workout_id = ?
            """,
            build_workout_values(request.form) + (workout_id,),
        )

    return redirect(url_for("index"))


@app.route("/workouts/<int:workout_id>/delete", methods=["POST"])
def delete_workout(workout_id: int) -> Any:
    with get_db() as conn:
        conn.execute("DELETE FROM workout_sessions WHERE workout_id = ?", (workout_id,))

    return redirect(url_for("index"))


@app.route("/profile", methods=["POST"])
def update_profile() -> Any:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE user_profiles
            SET age = ?, gender = ?
            WHERE user_id = ?
            """,
            (
                parse_optional_int(request.form.get("age")),
                parse_optional_text(request.form.get("gender")),
                DEFAULT_USER_ID,
            ),
        )

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)

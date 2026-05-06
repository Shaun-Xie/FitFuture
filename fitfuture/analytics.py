from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from . import config, datasets
from .db import fetch_all
from .users import get_user_profile
from .utils import parse_optional_int, parse_optional_text, parse_workout_date, get_week_start


def percentile_rank(series: pd.Series, value: float) -> float | None:
    cleaned_values = [float(item) for item in series if pd.notnull(item)]
    if not cleaned_values:
        return None

    count = sum(1 for item in cleaned_values if item <= value)
    return 100 * count / len(cleaned_values)


def fetch_recent_user_workouts(
    user_id: int = config.DEFAULT_USER_ID,
    window_days: int = 90,
) -> list[dict[str, Any]]:
    window_start = (date.today() - timedelta(days=window_days)).isoformat()

    return fetch_all(
        """
        SELECT
            workout_date,
            total_duration_minutes,
            perceived_intensity,
            recovery_rating,
            sleep_hours
        FROM workout_sessions
        WHERE user_id = ? AND workout_date >= ?
        ORDER BY workout_date ASC, workout_id ASC
        """,
        (user_id, window_start),
    )


def compute_fitness_summary(user_id: int = config.DEFAULT_USER_ID) -> dict[str, Any]:
    profile = get_user_profile(user_id) or {}
    result: dict[str, Any] = {"has_data": False}

    window_start = (date.today() - timedelta(days=config.ANALYTICS_WINDOW_DAYS)).isoformat()
    rows = fetch_all(
        """
        SELECT
            workout_date,
            total_duration_minutes,
            perceived_intensity,
            recovery_rating,
            sleep_hours
        FROM workout_sessions
        WHERE user_id = ? AND workout_date >= ? AND total_duration_minutes IS NOT NULL
        """,
        (user_id, window_start),
    )

    if rows:
        durations = [row["total_duration_minutes"] for row in rows]
        intensities = [
            row["perceived_intensity"]
            for row in rows
            if row.get("perceived_intensity") is not None
        ]
        recovery_ratings = [
            row["recovery_rating"]
            for row in rows
            if row.get("recovery_rating") is not None
        ]
        sleep_values = [
            row["sleep_hours"]
            for row in rows
            if row.get("sleep_hours") is not None
        ]
        total_minutes = sum(durations)
        average_duration = total_minutes / len(durations)

        workout_dates = [
            workout_date
            for row in rows
            if (workout_date := parse_workout_date(row["workout_date"])) is not None
        ]
        tracked_span_days = (
            max((max(workout_dates) - min(workout_dates)).days + 1, 1)
            if workout_dates
            else config.ANALYTICS_WINDOW_DAYS
        )

        weekly_minutes = total_minutes * 7 / tracked_span_days
        current_score = min(10, weekly_minutes / 30)
        projected_score = min(10, current_score + 1)

        result.update(
            has_data=True,
            session_count_30d=len(rows),
            total_minutes_30d=total_minutes,
            avg_duration=average_duration,
            avg_intensity=sum(intensities) / len(intensities) if intensities else None,
            avg_recovery_rating=(
                sum(recovery_ratings) / len(recovery_ratings) if recovery_ratings else None
            ),
            avg_sleep_hours=sum(sleep_values) / len(sleep_values) if sleep_values else None,
            weekly_minutes=weekly_minutes,
            current_score=current_score,
            projected_score=projected_score,
        )

    datasets.compute_external_stats()

    age = parse_optional_int(profile.get("age"))
    gender = parse_optional_text(profile.get("gender"))
    gender = gender.upper() if gender else None

    if age and gender and result.get("weekly_minutes"):
        result["cohort_label"] = f"{age - 2}-{age + 2}yo {'males' if gender == 'M' else 'females'}"

        df365 = datasets.DATAFRAMES.get("hf365")
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

        df_gym = datasets.DATAFRAMES.get("gym")
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


def build_training_recommendations(
    fitness_summary: dict[str, Any],
    training_insights: dict[str, Any],
    training_block_progress: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    if not fitness_summary.get("has_data"):
        return [
            {
                "label": "Foundation",
                "title": "Log three workouts this week",
                "body": "A few recent sessions are enough to unlock trend, intensity, and cohort analysis.",
            },
            {
                "label": "Data Quality",
                "title": "Add duration and effort every time",
                "body": "Those two fields power the score, projections, and training-zone breakdown.",
            },
        ]

    recommendations: list[dict[str, str]] = []
    training_block_progress = training_block_progress or {}
    weekly_target = float(
        training_block_progress.get("target_weekly_minutes")
        or config.WEEKLY_VOLUME_TARGET_MINUTES
    )
    target_label = (
        "block target"
        if training_block_progress.get("has_block")
        else "150-minute benchmark"
    )
    weekly_minutes = float(fitness_summary.get("weekly_minutes") or 0)
    avg_intensity = fitness_summary.get("avg_intensity")
    avg_recovery_rating = training_insights.get("avg_recovery_rating")
    avg_sleep_hours = training_insights.get("avg_sleep_hours")
    consistency_rate = float(training_insights.get("consistency_rate") or 0)
    active_week_streak = int(training_insights.get("active_week_streak") or 0)
    strain_risk_sessions = int(training_insights.get("strain_risk_sessions") or 0)

    if weekly_minutes < 90:
        recommendations.append(
            {
                "label": "Volume",
                "title": "Build toward a stronger weekly base",
                "body": "Aim for two or three 35-minute sessions before adding more intensity.",
            }
        )
    elif weekly_minutes < weekly_target:
        remaining = round(weekly_target - weekly_minutes)
        recommendations.append(
            {
                "label": "Volume",
                "title": f"Close a {remaining}-minute weekly gap",
                "body": f"One short conditioning session can move you closer to the {target_label}.",
            }
        )
    else:
        recommendations.append(
            {
                "label": "Volume",
                "title": "Maintain your current training load",
                "body": f"Your recent volume is above the {target_label}. Keep progression gradual.",
            }
        )

    if (
        training_block_progress.get("status") == "active"
        and training_block_progress.get("current_week_minutes_percent", 0) < 50
        and training_block_progress.get("percent_complete", 0) >= 25
    ):
        recommendations.append(
            {
                "label": "Block Pace",
                "title": "Bring this week back onto plan",
                "body": "Your active block is moving faster than your current-week volume. Add a controlled session before intensity.",
            }
        )
    elif (
        training_block_progress.get("status") == "active"
        and training_block_progress.get("effort_delta") is not None
        and training_block_progress["effort_delta"] >= 2
    ):
        recommendations.append(
            {
                "label": "Block Effort",
                "title": "Keep effort aligned with the phase",
                "body": "Your current week is running above the block target. Shift one workout down a notch to preserve adaptation.",
            }
        )

    if avg_recovery_rating is not None and (
        avg_recovery_rating <= 2.5 or strain_risk_sessions >= 2
    ):
        recommendations.append(
            {
                "label": "Readiness",
                "title": "Protect the next hard session",
                "body": "Recovery is trending low, so bias the next session toward mobility, sleep, or easy aerobic work.",
            }
        )
    elif avg_sleep_hours is not None and avg_sleep_hours < 6.5:
        recommendations.append(
            {
                "label": "Sleep",
                "title": "Raise the recovery floor",
                "body": "Your logged sleep is light. A steadier bedtime can improve readiness before adding intensity.",
            }
        )

    if avg_intensity is not None and avg_intensity >= 8:
        recommendations.append(
            {
                "label": "Recovery",
                "title": "Add a lower-intensity recovery slot",
                "body": "Your average effort is high, so one easier day can help sustain the block.",
            }
        )
    elif avg_intensity is not None and avg_intensity <= 4:
        recommendations.append(
            {
                "label": "Stimulus",
                "title": "Add one focused hard session",
                "body": "Your effort profile is light. A controlled higher-effort workout adds stimulus.",
            }
        )

    if consistency_rate < 50:
        recommendations.append(
            {
                "label": "Consistency",
                "title": "Anchor workouts to repeatable days",
                "body": "Pick two fixed days this week so the trend line has a steadier floor.",
            }
        )
    elif active_week_streak >= 3:
        recommendations.append(
            {
                "label": "Consistency",
                "title": f"Protect your {active_week_streak}-week streak",
                "body": "Schedule the next session early in the week to keep momentum intact.",
            }
        )

    return recommendations[:3]


def build_training_insights(user_id: int = config.DEFAULT_USER_ID) -> dict[str, Any]:
    rows = fetch_recent_user_workouts(
        user_id,
        window_days=config.TREND_WINDOW_WEEKS * 7,
    )
    today = date.today()
    first_week_start = get_week_start(today) - timedelta(weeks=config.TREND_WINDOW_WEEKS - 1)
    week_starts = [
        first_week_start + timedelta(weeks=index)
        for index in range(config.TREND_WINDOW_WEEKS)
    ]
    weekly_buckets: dict[date, dict[str, Any]] = {
        week_start: {
            "label": f"{week_start.month}/{week_start.day}",
            "minutes": 0,
            "sessions": 0,
            "intensity_total": 0,
            "intensity_count": 0,
        }
        for week_start in week_starts
    }
    intensity_zones = {
        "Recovery": 0,
        "Base": 0,
        "Hard": 0,
        "Peak": 0,
    }
    workout_days: set[date] = set()
    recovery_total = 0
    recovery_count = 0
    sleep_total = 0.0
    sleep_count = 0
    strain_risk_sessions = 0

    for row in rows:
        workout_day = parse_workout_date(row["workout_date"])
        if workout_day is None:
            continue

        workout_days.add(workout_day)
        week_start = get_week_start(workout_day)
        if week_start in weekly_buckets:
            weekly_buckets[week_start]["sessions"] += 1
            weekly_buckets[week_start]["minutes"] += row.get("total_duration_minutes") or 0

            if row.get("perceived_intensity") is not None:
                weekly_buckets[week_start]["intensity_total"] += row["perceived_intensity"]
                weekly_buckets[week_start]["intensity_count"] += 1

        recovery_rating = row.get("recovery_rating")
        if recovery_rating is not None:
            recovery_total += recovery_rating
            recovery_count += 1

        sleep_hours = row.get("sleep_hours")
        if sleep_hours is not None:
            sleep_total += sleep_hours
            sleep_count += 1

        intensity = row.get("perceived_intensity")
        if intensity is None:
            continue
        if intensity <= 3:
            intensity_zones["Recovery"] += 1
        elif intensity <= 6:
            intensity_zones["Base"] += 1
        elif intensity <= 8:
            intensity_zones["Hard"] += 1
        else:
            intensity_zones["Peak"] += 1

        if recovery_rating is not None and intensity >= 8 and recovery_rating <= 2:
            strain_risk_sessions += 1

    weeks = list(weekly_buckets.values())
    active_weeks = {
        week_start
        for week_start, bucket in weekly_buckets.items()
        if bucket["sessions"] > 0
    }
    active_week_streak = 0
    probe_week = get_week_start(today)
    while probe_week in active_weeks:
        active_week_streak += 1
        probe_week -= timedelta(weeks=1)

    best_week = max(weeks, key=lambda bucket: bucket["minutes"]) if weeks else None
    consistency_rate = 100 * len(active_weeks) / config.TREND_WINDOW_WEEKS

    return {
        "weekly_labels": [bucket["label"] for bucket in weeks],
        "weekly_minutes": [bucket["minutes"] for bucket in weeks],
        "weekly_sessions": [bucket["sessions"] for bucket in weeks],
        "weekly_avg_intensity": [
            (
                bucket["intensity_total"] / bucket["intensity_count"]
                if bucket["intensity_count"]
                else None
            )
            for bucket in weeks
        ],
        "intensity_labels": list(intensity_zones.keys()),
        "intensity_counts": list(intensity_zones.values()),
        "active_week_streak": active_week_streak,
        "consistency_rate": consistency_rate,
        "active_days": len(workout_days),
        "best_week_minutes": best_week["minutes"] if best_week else 0,
        "best_week_label": best_week["label"] if best_week else None,
        "avg_recovery_rating": recovery_total / recovery_count if recovery_count else None,
        "avg_sleep_hours": sleep_total / sleep_count if sleep_count else None,
        "recovery_samples": recovery_count,
        "sleep_samples": sleep_count,
        "strain_risk_sessions": strain_risk_sessions,
        "target_weekly_minutes": config.WEEKLY_VOLUME_TARGET_MINUTES,
    }


def build_chart_data(
    external_stats: dict[str, dict[str, Any]],
    fitness_summary: dict[str, Any],
    training_insights: dict[str, Any],
) -> dict[str, Any]:
    chart_data: dict[str, Any] = {
        "user_daily_exercise": None,
        "pop_daily_exercise": None,
        "user_avg_duration": None,
        "pop_avg_duration": None,
        "current_score": None,
        "projected_score": None,
        "weekly_labels": training_insights["weekly_labels"],
        "weekly_minutes": training_insights["weekly_minutes"],
        "weekly_sessions": training_insights["weekly_sessions"],
        "intensity_labels": training_insights["intensity_labels"],
        "intensity_counts": training_insights["intensity_counts"],
        "target_weekly_minutes": training_insights["target_weekly_minutes"],
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

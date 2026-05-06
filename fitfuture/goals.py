from __future__ import annotations

from datetime import datetime
from typing import Any

from . import config
from .db import dict_or_none, fetch_one, get_db


def get_user_goals(user_id: int) -> dict[str, Any]:
    goals = fetch_one("SELECT * FROM user_goals WHERE user_id = ?", (user_id,))
    if goals is not None:
        return goals

    save_user_goals(
        user_id,
        config.DEFAULT_WEEKLY_MINUTES_GOAL,
        config.DEFAULT_WEEKLY_SESSIONS_GOAL,
    )
    return fetch_one("SELECT * FROM user_goals WHERE user_id = ?", (user_id,))


def save_user_goals(
    user_id: int,
    weekly_minutes_goal: int,
    weekly_sessions_goal: int,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO user_goals
            (user_id, weekly_minutes_goal, weekly_sessions_goal, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                weekly_minutes_goal = excluded.weekly_minutes_goal,
                weekly_sessions_goal = excluded.weekly_sessions_goal,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                weekly_minutes_goal,
                weekly_sessions_goal,
                datetime.utcnow().isoformat(),
            ),
        )


def build_goal_progress(
    goals: dict[str, Any],
    training_insights: dict[str, Any],
) -> dict[str, Any]:
    current_week_minutes = (
        training_insights["weekly_minutes"][-1]
        if training_insights.get("weekly_minutes")
        else 0
    )
    current_week_sessions = (
        training_insights["weekly_sessions"][-1]
        if training_insights.get("weekly_sessions")
        else 0
    )
    minutes_goal = goals["weekly_minutes_goal"]
    sessions_goal = goals["weekly_sessions_goal"]

    return {
        "weekly_minutes_goal": minutes_goal,
        "weekly_sessions_goal": sessions_goal,
        "current_week_minutes": current_week_minutes,
        "current_week_sessions": current_week_sessions,
        "minutes_percent": min(100, round(100 * current_week_minutes / minutes_goal))
        if minutes_goal
        else 0,
        "sessions_percent": min(100, round(100 * current_week_sessions / sessions_goal))
        if sessions_goal
        else 0,
    }


def build_personal_records(
    user_id: int,
    training_insights: dict[str, Any],
) -> dict[str, Any]:
    with get_db() as conn:
        longest = conn.execute(
            """
            SELECT workout_date, total_duration_minutes
            FROM workout_sessions
            WHERE user_id = ? AND total_duration_minutes IS NOT NULL
            ORDER BY total_duration_minutes DESC, workout_date DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        highest_effort = conn.execute(
            """
            SELECT workout_date, perceived_intensity
            FROM workout_sessions
            WHERE user_id = ? AND perceived_intensity IS NOT NULL
            ORDER BY perceived_intensity DESC, workout_date DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        total_sessions = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM workout_sessions
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    longest = dict_or_none(longest)
    highest_effort = dict_or_none(highest_effort)
    total_sessions = dict_or_none(total_sessions)

    return {
        "longest_session_minutes": longest["total_duration_minutes"] if longest else None,
        "longest_session_date": longest["workout_date"] if longest else None,
        "highest_effort": highest_effort["perceived_intensity"] if highest_effort else None,
        "highest_effort_date": highest_effort["workout_date"] if highest_effort else None,
        "best_week_minutes": training_insights.get("best_week_minutes", 0),
        "active_week_streak": training_insights.get("active_week_streak", 0),
        "total_sessions": total_sessions["c"] if total_sessions else 0,
    }

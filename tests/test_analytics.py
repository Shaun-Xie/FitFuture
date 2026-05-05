from __future__ import annotations

from datetime import date, timedelta

import main
from conftest import register


def insert_workout(
    user_id: int,
    workout_date: date,
    duration: int,
    intensity: int,
) -> None:
    with main.get_db() as conn:
        conn.execute(
            """
            INSERT INTO workout_sessions
            (user_id, workout_date, total_duration_minutes, perceived_intensity, source, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                workout_date.isoformat(),
                duration,
                intensity,
                "manual",
                "analytics fixture",
            ),
        )


def test_fitness_summary_uses_recent_user_workouts(client):
    register(client, "analytics@example.com", "password123")
    user = main.fetch_one("SELECT * FROM users WHERE email = ?", ("analytics@example.com",))

    today = date.today()
    insert_workout(user["user_id"], today - timedelta(days=6), 30, 6)
    insert_workout(user["user_id"], today, 60, 8)

    summary = main.compute_fitness_summary(user["user_id"])

    assert summary["has_data"] is True
    assert summary["session_count_30d"] == 2
    assert summary["total_minutes_30d"] == 90
    assert summary["avg_duration"] == 45
    assert summary["avg_intensity"] == 7
    assert round(summary["weekly_minutes"], 1) == 90
    assert summary["current_score"] == 3
    assert summary["projected_score"] == 4


def test_training_insights_builds_trend_and_intensity_zones(client):
    register(client, "trend@example.com", "password123")
    user = main.fetch_one("SELECT * FROM users WHERE email = ?", ("trend@example.com",))

    today = date.today()
    insert_workout(user["user_id"], today - timedelta(days=14), 20, 3)
    insert_workout(user["user_id"], today - timedelta(days=7), 40, 5)
    insert_workout(user["user_id"], today, 60, 9)

    insights = main.build_training_insights(user["user_id"])

    assert len(insights["weekly_labels"]) == main.TREND_WINDOW_WEEKS
    assert sum(insights["weekly_minutes"]) == 120
    assert sum(insights["weekly_sessions"]) == 3
    assert insights["active_days"] == 3
    assert insights["best_week_minutes"] == 60
    assert insights["intensity_labels"] == ["Recovery", "Base", "Hard", "Peak"]
    assert insights["intensity_counts"] == [1, 1, 0, 1]


def test_recommendations_reflect_training_state():
    recommendations = main.build_training_recommendations(
        {
            "has_data": True,
            "weekly_minutes": 65,
            "avg_intensity": 8.5,
        },
        {
            "consistency_rate": 25,
            "active_week_streak": 1,
        },
    )

    labels = [recommendation["label"] for recommendation in recommendations]
    assert labels == ["Volume", "Recovery", "Consistency"]

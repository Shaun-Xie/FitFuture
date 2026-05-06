from __future__ import annotations

from datetime import date, timedelta

from conftest import register
from fitfuture import analytics, config, db, goals


def insert_workout(
    user_id: int,
    workout_date: date,
    duration: int,
    intensity: int,
    recovery: int | None = None,
    sleep_hours: float | None = None,
) -> None:
    with db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO workout_sessions
            (user_id, workout_date, total_duration_minutes, perceived_intensity,
             recovery_rating, sleep_hours, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                workout_date.isoformat(),
                duration,
                intensity,
                recovery,
                sleep_hours,
                "manual",
                "analytics fixture",
            ),
        )


def test_fitness_summary_uses_recent_user_workouts(client):
    register(client, "analytics@example.com", "password123")
    user = db.fetch_one("SELECT * FROM users WHERE email = ?", ("analytics@example.com",))

    today = date.today()
    insert_workout(user["user_id"], today - timedelta(days=6), 30, 6, 4, 7.5)
    insert_workout(user["user_id"], today, 60, 8, 3, 6.5)

    summary = analytics.compute_fitness_summary(user["user_id"])

    assert summary["has_data"] is True
    assert summary["session_count_30d"] == 2
    assert summary["total_minutes_30d"] == 90
    assert summary["avg_duration"] == 45
    assert summary["avg_intensity"] == 7
    assert summary["avg_recovery_rating"] == 3.5
    assert summary["avg_sleep_hours"] == 7
    assert round(summary["weekly_minutes"], 1) == 90
    assert summary["current_score"] == 3
    assert summary["projected_score"] == 4


def test_training_insights_builds_trend_and_intensity_zones(client):
    register(client, "trend@example.com", "password123")
    user = db.fetch_one("SELECT * FROM users WHERE email = ?", ("trend@example.com",))

    today = date.today()
    insert_workout(user["user_id"], today - timedelta(days=14), 20, 3, 5, 8)
    insert_workout(user["user_id"], today - timedelta(days=7), 40, 5, 3, 7)
    insert_workout(user["user_id"], today, 60, 9, 2, 5.5)

    insights = analytics.build_training_insights(user["user_id"])

    assert len(insights["weekly_labels"]) == config.TREND_WINDOW_WEEKS
    assert sum(insights["weekly_minutes"]) == 120
    assert sum(insights["weekly_sessions"]) == 3
    assert insights["active_days"] == 3
    assert insights["best_week_minutes"] == 60
    assert insights["intensity_labels"] == ["Recovery", "Base", "Hard", "Peak"]
    assert insights["intensity_counts"] == [1, 1, 0, 1]
    assert round(insights["avg_recovery_rating"], 1) == 3.3
    assert round(insights["avg_sleep_hours"], 1) == 6.8
    assert insights["strain_risk_sessions"] == 1


def test_recommendations_reflect_training_state():
    recommendations = analytics.build_training_recommendations(
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


def test_recommendations_use_recovery_readiness():
    recommendations = analytics.build_training_recommendations(
        {
            "has_data": True,
            "weekly_minutes": 155,
            "avg_intensity": 7,
        },
        {
            "avg_recovery_rating": 2.2,
            "avg_sleep_hours": 6.1,
            "consistency_rate": 75,
            "active_week_streak": 1,
            "strain_risk_sessions": 2,
        },
    )

    assert recommendations[1]["label"] == "Readiness"


def test_goal_progress_and_personal_records(client):
    register(client, "records@example.com", "password123")
    user = db.fetch_one("SELECT * FROM users WHERE email = ?", ("records@example.com",))
    user_goals = goals.get_user_goals(user["user_id"])

    today = date.today()
    insert_workout(user["user_id"], today - timedelta(days=1), 45, 6)
    insert_workout(user["user_id"], today, 75, 9)

    insights = analytics.build_training_insights(user["user_id"])
    progress = goals.build_goal_progress(user_goals, insights)
    records = goals.build_personal_records(user["user_id"], insights)

    assert progress["current_week_minutes"] == 120
    assert progress["current_week_sessions"] == 2
    assert progress["minutes_percent"] == 80
    assert progress["sessions_percent"] == 67
    assert records["longest_session_minutes"] == 75
    assert records["highest_effort"] == 9
    assert records["total_sessions"] == 2

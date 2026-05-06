from __future__ import annotations

from conftest import login, register
from fitfuture import db


def test_protected_routes_redirect_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login?next=/"


def test_demo_user_can_log_in_and_view_dashboard(client):
    response = login(client)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert b"FitFuture Training Console" in dashboard.data


def test_registration_creates_profile_and_session(client):
    response = register(client, "new@example.com", "password123")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    user = db.fetch_one("SELECT * FROM users WHERE email = ?", ("new@example.com",))
    assert user is not None

    profile = db.fetch_one(
        "SELECT * FROM user_profiles WHERE user_id = ?",
        (user["user_id"],),
    )
    assert profile is not None
    goals = db.fetch_one(
        "SELECT * FROM user_goals WHERE user_id = ?",
        (user["user_id"],),
    )
    assert goals["weekly_minutes_goal"] == 150
    assert goals["weekly_sessions_goal"] == 3

    dashboard = client.get("/")
    assert dashboard.status_code == 200


def test_registration_validation_shows_user_facing_error(client):
    response = register(client, "not-an-email", "short")

    assert response.status_code == 400
    assert b"Enter a valid email address." in response.data
    assert b"Password must be at least 8 characters." in response.data


def test_workout_creation_uses_logged_in_user_not_form_user_id(client):
    register(client, "owner@example.com", "password123")
    owner = db.fetch_one("SELECT * FROM users WHERE email = ?", ("owner@example.com",))

    response = client.post(
        "/workouts",
        data={
            "user_id": "999",
            "workout_date": "2026-05-05",
            "start_time": "08:00",
            "end_time": "08:45",
            "total_duration_minutes": "45",
            "perceived_intensity": "7",
            "recovery_rating": "4",
            "sleep_hours": "7.5",
            "source": "manual",
            "notes": "Ownership test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    workout = db.fetch_one("SELECT * FROM workout_sessions WHERE notes = ?", ("Ownership test",))
    assert workout is not None
    assert workout["user_id"] == owner["user_id"]
    assert workout["recovery_rating"] == 4
    assert workout["sleep_hours"] == 7.5


def test_workout_validation_rejects_bad_input(client):
    register(client, "validation@example.com", "password123")

    response = client.post(
        "/workouts",
        data={
            "workout_date": "",
            "total_duration_minutes": "0",
            "perceived_intensity": "11",
            "recovery_rating": "6",
            "sleep_hours": "18",
            "source": "spreadsheet",
            "notes": "Invalid workout",
        },
    )

    assert response.status_code == 400
    assert b"Workout date is required." in response.data
    assert b"Duration must be between 1 and 600 minutes." in response.data
    assert b"Effort must be between 1 and 10." in response.data
    assert b"Recovery must be between 1 and 5." in response.data
    assert b"Sleep must be between 0 and 16 hours." in response.data
    assert b"Source must be manual, app, device, or blank." in response.data

    workout = db.fetch_one("SELECT * FROM workout_sessions WHERE notes = ?", ("Invalid workout",))
    assert workout is None


def test_profile_validation_rejects_bad_input(client):
    register(client, "profile@example.com", "password123")

    response = client.post(
        "/profile",
        data={"age": "9", "gender": "X"},
    )

    assert response.status_code == 400
    assert b"Age must be between 10 and 90." in response.data
    assert b"Gender must be male, female, or not set." in response.data


def test_goal_update_persists_user_targets(client):
    register(client, "goals@example.com", "password123")
    user = db.fetch_one("SELECT * FROM users WHERE email = ?", ("goals@example.com",))

    response = client.post(
        "/goals",
        data={"weekly_minutes_goal": "210", "weekly_sessions_goal": "5"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    goals = db.fetch_one(
        "SELECT * FROM user_goals WHERE user_id = ?",
        (user["user_id"],),
    )
    assert goals["weekly_minutes_goal"] == 210
    assert goals["weekly_sessions_goal"] == 5


def test_goal_validation_rejects_bad_targets(client):
    register(client, "badgoals@example.com", "password123")

    response = client.post(
        "/goals",
        data={"weekly_minutes_goal": "10", "weekly_sessions_goal": "20"},
    )

    assert response.status_code == 400
    assert b"Weekly minutes goal must be between 30 and 600." in response.data
    assert b"Weekly sessions goal must be between 1 and 14." in response.data


def test_users_cannot_edit_or_delete_each_others_workouts(client):
    register(client, "owner@example.com", "password123")
    owner = db.fetch_one("SELECT * FROM users WHERE email = ?", ("owner@example.com",))

    client.post(
        "/workouts",
        data={
            "workout_date": "2026-05-05",
            "total_duration_minutes": "45",
            "perceived_intensity": "7",
            "source": "manual",
            "notes": "Private session",
        },
    )
    workout = db.fetch_one(
        "SELECT * FROM workout_sessions WHERE user_id = ?",
        (owner["user_id"],),
    )

    client.get("/logout")
    register(client, "other@example.com", "password123")

    edit_response = client.get(f"/workouts/{workout['workout_id']}/edit")
    assert edit_response.status_code == 404

    delete_response = client.post(
        f"/workouts/{workout['workout_id']}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 302

    still_exists = db.fetch_one(
        "SELECT * FROM workout_sessions WHERE workout_id = ?",
        (workout["workout_id"],),
    )
    assert still_exists is not None

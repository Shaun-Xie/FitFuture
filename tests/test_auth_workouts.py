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

    dashboard = client.get("/")
    assert dashboard.status_code == 200


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
            "source": "manual",
            "notes": "Ownership test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    workout = db.fetch_one("SELECT * FROM workout_sessions WHERE notes = ?", ("Ownership test",))
    assert workout is not None
    assert workout["user_id"] == owner["user_id"]


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

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
    assert b"Log workouts and review your history" in dashboard.data


def test_plan_page_separates_planning_workspace(client):
    register(client, "plan@example.com", "password123")

    response = client.get("/plan")

    assert response.status_code == 200
    assert b"Set a clear workout target" in response.data
    assert b"Current Training Block" in response.data


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

    workout = db.fetch_one(
        "SELECT * FROM workout_sessions WHERE notes = ?", ("Ownership test",)
    )
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
    assert b"Intensity must be between 1 and 10." in response.data
    assert b"Recovery must be between 1 and 5." in response.data
    assert b"Sleep must be between 0 and 16 hours." in response.data
    assert b"Source must be manual, app, device, or blank." in response.data

    workout = db.fetch_one(
        "SELECT * FROM workout_sessions WHERE notes = ?", ("Invalid workout",)
    )
    assert workout is None


def test_sleep_page_logs_recovery_separately(client):
    register(client, "sleep@example.com", "password123")
    user = db.fetch_one("SELECT * FROM users WHERE email = ?", ("sleep@example.com",))

    page = client.get("/sleep")
    assert page.status_code == 200
    assert b"Log sleep and recovery" in page.data

    response = client.post(
        "/sleep",
        data={
            "sleep_date": "2026-05-06",
            "sleep_hours": "7.5",
            "recovery_rating": "4",
            "notes": "Slept well",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    sleep_log = db.fetch_one(
        "SELECT * FROM sleep_logs WHERE notes = ?", ("Slept well",)
    )
    assert sleep_log is not None
    assert sleep_log["user_id"] == user["user_id"]
    assert sleep_log["sleep_hours"] == 7.5
    assert sleep_log["recovery_rating"] == 4


def test_goal_update_calculates_total_from_workouts_and_duration(client):
    register(client, "calculatedgoals@example.com", "password123")
    user = db.fetch_one(
        "SELECT * FROM users WHERE email = ?", ("calculatedgoals@example.com",)
    )

    response = client.post(
        "/goals",
        data={"workouts_per_week": "4", "workout_duration_minutes": "45"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    goals = db.fetch_one(
        "SELECT * FROM user_goals WHERE user_id = ?",
        (user["user_id"],),
    )
    assert goals["weekly_minutes_goal"] == 180
    assert goals["weekly_sessions_goal"] == 4


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
    assert b"Total weekly minutes goal must be between 30 and 900." in response.data
    assert b"Workouts per week goal must be between 1 and 14." in response.data


def test_training_block_update_persists_current_phase(client):
    register(client, "block@example.com", "password123")
    user = db.fetch_one("SELECT * FROM users WHERE email = ?", ("block@example.com",))

    response = client.post(
        "/training-block",
        data={
            "block_name": "Base Build",
            "training_focus": "hybrid",
            "start_date": "2026-05-04",
            "end_date": "2026-06-14",
            "workouts_per_week": "5",
            "workout_duration_minutes": "48",
            "notes": "Six-week base block",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    block = db.fetch_one(
        "SELECT * FROM training_blocks WHERE user_id = ? AND status = 'active'",
        (user["user_id"],),
    )
    assert block["block_name"] == "Base Build"
    assert block["training_focus"] == "hybrid"
    assert block["target_weekly_minutes"] == 240
    assert block["target_weekly_sessions"] == 5
    assert block["target_effort"] is None

    response = client.post(
        "/training-block",
        data={
            "block_name": "Peak Block",
            "training_focus": "strength",
            "start_date": "2026-06-15",
            "end_date": "2026-07-12",
            "target_weekly_minutes": "180",
            "target_weekly_sessions": "4",
            "target_effort": "8",
            "notes": "Save as new phase",
            "save_mode": "new",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    blocks = db.fetch_all(
        "SELECT status FROM training_blocks WHERE user_id = ? ORDER BY block_id",
        (user["user_id"],),
    )
    assert [block["status"] for block in blocks] == ["completed", "active"]


def test_training_block_validation_rejects_bad_input(client):
    register(client, "badblock@example.com", "password123")

    response = client.post(
        "/training-block",
        data={
            "block_name": "",
            "training_focus": "chaos",
            "start_date": "2026-08-01",
            "end_date": "2026-07-01",
            "target_weekly_minutes": "10",
            "target_weekly_sessions": "0",
            "target_effort": "11",
            "notes": "Invalid block",
        },
    )

    assert response.status_code == 400
    assert b"Block name is required." in response.data
    assert b"Training focus must be one of the available options." in response.data
    assert b"Block end date must be on or after the start date." in response.data
    assert b"Total weekly minutes target must be between 30 and 900." in response.data
    assert b"Workouts per week target must be between 1 and 14." in response.data
    assert b"Block target effort must be between 1 and 10." in response.data


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

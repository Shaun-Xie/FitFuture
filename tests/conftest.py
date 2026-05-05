from __future__ import annotations

import pytest

import main


@pytest.fixture()
def isolated_app(tmp_path, monkeypatch):
    db_path = tmp_path / "fitfuture-test.db"

    monkeypatch.setattr(main, "DB_PATH", db_path)
    monkeypatch.setattr(main, "EXTERNAL_STATS", {})
    monkeypatch.setattr(main, "DATAFRAMES", {})
    monkeypatch.setattr(main, "compute_external_stats", lambda: {})

    main.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    main.init_db()

    yield main.app

    main.app.config.update(TESTING=False)


@pytest.fixture()
def client(isolated_app):
    return isolated_app.test_client()


def register(client, email: str = "athlete@example.com", password: str = "password123"):
    return client.post(
        "/register",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def login(client, email: str = main.DEMO_USER_EMAIL, password: str = main.DEMO_USER_PASSWORD):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )

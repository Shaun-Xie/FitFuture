from __future__ import annotations

import pytest

from fitfuture import create_app
from fitfuture import config, datasets, db


@pytest.fixture()
def isolated_app(tmp_path, monkeypatch):
    db_path = tmp_path / "fitfuture-test.db"

    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(datasets, "EXTERNAL_STATS", {})
    monkeypatch.setattr(datasets, "DATAFRAMES", {})
    monkeypatch.setattr(datasets, "compute_external_stats", lambda: {})

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})

    yield app


@pytest.fixture()
def client(isolated_app):
    return isolated_app.test_client()


def register(client, email: str = "athlete@example.com", password: str = "password123"):
    return client.post(
        "/register",
        data={"email": email, "password": password},
        follow_redirects=False,
    )

def login(
    client,
    email: str = config.DEMO_USER_EMAIL,
    password: str = config.DEMO_USER_PASSWORD,
):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )

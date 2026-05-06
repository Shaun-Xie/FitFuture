from __future__ import annotations

from fitfuture import config, db


def test_init_db_records_schema_migration(client):
    migrations = db.fetch_all(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    )

    assert migrations == [
        {"version": 1, "name": "initial_schema"},
        {"version": 2, "name": "user_goals"},
        {"version": 3, "name": "recovery_tracking"},
        {"version": 4, "name": "training_blocks"},
    ]


def test_init_db_is_idempotent(client):
    db.init_db()
    db.init_db()

    migration_count = db.fetch_one("SELECT COUNT(*) AS c FROM schema_migrations")
    demo_user_count = db.fetch_one(
        "SELECT COUNT(*) AS c FROM users WHERE email = ?",
        (config.DEMO_USER_EMAIL,),
    )

    assert migration_count["c"] == 4
    assert demo_user_count["c"] == 1

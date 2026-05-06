from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from werkzeug.security import generate_password_hash

from . import config

DB_PATH = config.DB_PATH


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def dict_or_none(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
    return dict_or_none(row)


def fetch_all(
    query: str,
    params: list[Any] | tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def migration_001_initial_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            bmi REAL,
            resting_heart_rate REAL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS workout_sessions (
            workout_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workout_date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            total_duration_minutes INTEGER,
            perceived_intensity INTEGER,
            source TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        """
    )


def migration_002_user_goals(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_goals (
            user_id INTEGER PRIMARY KEY,
            weekly_minutes_goal INTEGER NOT NULL DEFAULT 150,
            weekly_sessions_goal INTEGER NOT NULL DEFAULT 3,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        """
    )


def add_column_if_missing(
    cursor: sqlite3.Cursor,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    existing_columns = {
        row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def migration_003_recovery_tracking(cursor: sqlite3.Cursor) -> None:
    add_column_if_missing(
        cursor,
        "workout_sessions",
        "recovery_rating",
        "recovery_rating INTEGER",
    )
    add_column_if_missing(
        cursor,
        "workout_sessions",
        "sleep_hours",
        "sleep_hours REAL",
    )


def migration_004_training_blocks(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_training_blocks (
            user_id INTEGER PRIMARY KEY,
            block_name TEXT NOT NULL,
            training_focus TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            target_weekly_minutes INTEGER NOT NULL,
            target_weekly_sessions INTEGER NOT NULL,
            target_effort INTEGER,
            notes TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        """
    )


MIGRATIONS = (
    (1, "initial_schema", migration_001_initial_schema),
    (2, "user_goals", migration_002_user_goals),
    (3, "recovery_tracking", migration_003_recovery_tracking),
    (4, "training_blocks", migration_004_training_blocks),
)


def ensure_migrations_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )


def run_migrations(cursor: sqlite3.Cursor) -> None:
    ensure_migrations_table(cursor)
    applied_versions = {
        row["version"]
        for row in cursor.execute("SELECT version FROM schema_migrations").fetchall()
    }

    for version, name, migration in MIGRATIONS:
        if version in applied_versions:
            continue

        migration(cursor)
        cursor.execute(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (version, name, datetime.utcnow().isoformat()),
        )


def ensure_default_user(cursor: sqlite3.Cursor) -> int:
    cursor.execute("SELECT * FROM users WHERE email = ?", (config.DEMO_USER_EMAIL,))
    user = cursor.fetchone()
    password_hash = generate_password_hash(config.DEMO_USER_PASSWORD)

    if user is None:
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, created_at, status)
            VALUES (?, ?, ?, ?)
            """,
            (
                config.DEMO_USER_EMAIL,
                password_hash,
                datetime.utcnow().isoformat(),
                "ACTIVE",
            ),
        )
        return int(cursor.lastrowid)

    if user["password_hash"] == "hash":
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (password_hash, user["user_id"]),
        )

    return int(user["user_id"])


def ensure_default_profile(
    cursor: sqlite3.Cursor,
    user_id: int = config.DEFAULT_USER_ID,
) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM user_profiles WHERE user_id = ?", (user_id,))
    if cursor.fetchone()["c"] == 0:
        cursor.execute(
            """
            INSERT INTO user_profiles (user_id, age, gender)
            VALUES (?, ?, ?)
            """,
            (user_id, 22, "M"),
        )


def ensure_default_goals(
    cursor: sqlite3.Cursor,
    user_id: int = config.DEFAULT_USER_ID,
) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM user_goals WHERE user_id = ?", (user_id,))
    if cursor.fetchone()["c"] == 0:
        cursor.execute(
            """
            INSERT INTO user_goals
            (user_id, weekly_minutes_goal, weekly_sessions_goal, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                config.DEFAULT_WEEKLY_MINUTES_GOAL,
                config.DEFAULT_WEEKLY_SESSIONS_GOAL,
                datetime.utcnow().isoformat(),
            ),
        )


def init_db() -> None:
    with get_db() as conn:
        cur = conn.cursor()
        run_migrations(cur)
        default_user_id = ensure_default_user(cur)
        ensure_default_profile(cur, default_user_id)
        ensure_default_goals(cur, default_user_id)

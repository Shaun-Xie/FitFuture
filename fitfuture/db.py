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


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def fetch_all(
    query: str,
    params: list[Any] | tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


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


def init_db() -> None:
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        default_user_id = ensure_default_user(cur)
        ensure_default_profile(cur, default_user_id)

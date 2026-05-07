from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .db import fetch_all, fetch_one, get_db
from .utils import parse_workout_date

TRAINING_FOCUS_OPTIONS = (
    ("strength", "Strength"),
    ("conditioning", "Conditioning"),
    ("hybrid", "Hybrid"),
    ("endurance", "Endurance"),
    ("mobility", "Mobility"),
    ("fat_loss", "Fat Loss"),
)
TRAINING_FOCUS_LABELS = dict(TRAINING_FOCUS_OPTIONS)
ALLOWED_TRAINING_FOCUSES = set(TRAINING_FOCUS_LABELS)


def get_training_block(user_id: int) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT *
        FROM training_blocks
        WHERE user_id = ? AND status = 'active'
        ORDER BY updated_at DESC, block_id DESC
        LIMIT 1
        """,
        (user_id,),
    )


def archive_current_training_block(user_id: int) -> None:
    current_block = get_training_block(user_id)
    if current_block is None:
        return

    timestamp = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE training_blocks
            SET status = 'completed', archived_at = ?, updated_at = ?
            WHERE block_id = ? AND user_id = ?
            """,
            (
                timestamp,
                timestamp,
                current_block["block_id"],
                user_id,
            ),
        )


def save_training_block(
    user_id: int,
    values: dict[str, Any],
    *,
    start_new: bool = False,
) -> None:
    current_block = get_training_block(user_id)
    timestamp = datetime.utcnow().isoformat()

    if current_block is not None and not start_new:
        with get_db() as conn:
            conn.execute(
                """
                UPDATE training_blocks
                SET block_name = ?, training_focus = ?, start_date = ?, end_date = ?,
                    target_weekly_minutes = ?, target_weekly_sessions = ?,
                    target_effort = ?, notes = ?, updated_at = ?
                WHERE block_id = ? AND user_id = ?
                """,
                (
                    values["block_name"],
                    values["training_focus"],
                    values["start_date"],
                    values["end_date"],
                    values["target_weekly_minutes"],
                    values["target_weekly_sessions"],
                    values["target_effort"],
                    values["notes"],
                    timestamp,
                    current_block["block_id"],
                    user_id,
                ),
            )
        return

    if current_block is not None:
        archive_current_training_block(user_id)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO training_blocks
            (user_id, block_name, training_focus, start_date, end_date,
             target_weekly_minutes, target_weekly_sessions, target_effort,
             notes, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                user_id,
                values["block_name"],
                values["training_focus"],
                values["start_date"],
                values["end_date"],
                values["target_weekly_minutes"],
                values["target_weekly_sessions"],
                values["target_effort"],
                values["notes"],
                timestamp,
                timestamp,
            ),
        )


def list_training_blocks(user_id: int, limit: int = 6) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT *
        FROM training_blocks
        WHERE user_id = ?
        ORDER BY
            CASE WHEN status = 'active' THEN 0 ELSE 1 END,
            updated_at DESC,
            block_id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    return [decorate_training_block(row) for row in rows]


def decorate_training_block(block: dict[str, Any]) -> dict[str, Any]:
    status = block.get("status", "active")
    return {
        **block,
        "focus_label": TRAINING_FOCUS_LABELS.get(
            block["training_focus"],
            block["training_focus"].replace("_", " ").title(),
        ),
        "status_label": "Current" if status == "active" else "Completed",
    }


def _latest_number(values: list[Any]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return float(value)
    return None


def build_training_block_progress(
    block: dict[str, Any] | None,
    training_insights: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    if block is None:
        return {"has_block": False}

    training_insights = training_insights or {}
    today = today or date.today()
    start_date = parse_workout_date(block["start_date"])
    end_date = parse_workout_date(block["end_date"])

    if start_date is None or end_date is None:
        return {"has_block": False}

    total_days = max((end_date - start_date).days + 1, 1)
    elapsed_days = min(max((today - start_date).days + 1, 0), total_days)
    days_until_start = max((start_date - today).days, 0)
    days_remaining = max((end_date - today).days, 0)

    if today < start_date:
        status = "planned"
        status_label = "Planned"
    elif today > end_date:
        status = "complete"
        status_label = "Complete"
    else:
        status = "active"
        status_label = "Active"

    current_week_minutes = (
        training_insights.get("weekly_minutes", [0])[-1]
        if training_insights.get("weekly_minutes")
        else 0
    )
    current_week_sessions = (
        training_insights.get("weekly_sessions", [0])[-1]
        if training_insights.get("weekly_sessions")
        else 0
    )
    current_week_avg_intensity = _latest_number(
        training_insights.get("weekly_avg_intensity", [])
    )
    target_effort = block.get("target_effort")

    return {
        "has_block": True,
        "block_name": block["block_name"],
        "training_focus": block["training_focus"],
        "focus_label": TRAINING_FOCUS_LABELS.get(
            block["training_focus"],
            block["training_focus"].replace("_", " ").title(),
        ),
        "start_date": block["start_date"],
        "end_date": block["end_date"],
        "status": status,
        "status_label": status_label,
        "total_days": total_days,
        "elapsed_days": elapsed_days,
        "days_until_start": days_until_start,
        "days_remaining": days_remaining,
        "percent_complete": round(100 * elapsed_days / total_days),
        "target_weekly_minutes": block["target_weekly_minutes"],
        "target_weekly_sessions": block["target_weekly_sessions"],
        "target_effort": target_effort,
        "current_week_minutes": current_week_minutes,
        "current_week_sessions": current_week_sessions,
        "current_week_avg_intensity": current_week_avg_intensity,
        "current_week_minutes_percent": min(
            100,
            round(100 * current_week_minutes / block["target_weekly_minutes"]),
        ),
        "current_week_sessions_percent": min(
            100,
            round(100 * current_week_sessions / block["target_weekly_sessions"]),
        ),
        "effort_delta": (
            current_week_avg_intensity - target_effort
            if current_week_avg_intensity is not None and target_effort is not None
            else None
        ),
    }

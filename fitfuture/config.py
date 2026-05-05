from __future__ import annotations

import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "fitfuture.db"

DEFAULT_USER_ID = 1
DEMO_USER_EMAIL = "test@example.com"
DEMO_USER_PASSWORD = "fitfuture123"

ANALYTICS_WINDOW_DAYS = 30
TREND_WINDOW_WEEKS = 8
WEEKLY_VOLUME_TARGET_MINUTES = 150

SECRET_KEY = os.environ.get("FITFUTURE_SECRET_KEY", "dev-fitfuture-secret-key")

DATASET_CONFIG: tuple[dict[str, Any], ...] = (
    {
        "filename": "gym_members_exercise_tracking.csv",
        "key": "gym",
        "label": "Gym Members Exercise Tracking",
        "usecols": ["Age", "Gender", "Session_Duration (hours)"],
        "metrics": {
            "Session_Duration (hours)": "avg_session_hours",
        },
    },
    {
        "filename": "health_fitness_tracking_365days.csv",
        "key": "hf365",
        "label": "Health Fitness Tracking 365 Days",
        "usecols": ["age", "gender", "steps", "exercise_minutes"],
        "metrics": {
            "steps": "avg_steps",
            "exercise_minutes": "avg_exercise_minutes",
        },
    },
    {
        "filename": "health_fitness_dataset.csv",
        "key": "health",
        "label": "General Health + Wellness Dataset",
        "usecols": ["daily_steps", "hours_sleep", "resting_heart_rate"],
        "metrics": {
            "daily_steps": "avg_steps",
            "hours_sleep": "avg_sleep_hours",
            "resting_heart_rate": "avg_resting_hr",
        },
    },
)

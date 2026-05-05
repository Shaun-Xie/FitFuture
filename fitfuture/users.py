from __future__ import annotations

from typing import Any

from .db import fetch_one


def get_user_profile(user_id: int) -> dict[str, Any] | None:
    return fetch_one("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))

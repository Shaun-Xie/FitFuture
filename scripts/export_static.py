"""Export a read-only FitFuture demo snapshot for static hosting.

The Flask app is interactive when run on a Python server. GitHub Pages can only
host static files, so this script renders representative demo pages with Flask's
test client, rewrites internal links for a Pages base path, and copies assets.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fitfuture import config  # noqa: E402
from fitfuture import db  # noqa: E402
from fitfuture import create_app  # noqa: E402

STATIC_ROUTES: tuple[tuple[str, str, bool], ...] = (
    ("/", "index.html", True),
    ("/sleep", "sleep/index.html", True),
    ("/plan", "plan/index.html", True),
    ("/analytics", "analytics/index.html", True),
    ("/login", "login/index.html", False),
    ("/register", "register/index.html", False),
)

INTERNAL_PATHS = {
    "/": "",
    "/sleep": "sleep/",
    "/plan": "plan/",
    "/analytics": "analytics/",
    "/login": "login/",
    "/register": "register/",
    "/logout": "login/",
}


def normalize_base_path(base_path: str) -> str:
    if not base_path or base_path == "/":
        return "/"
    return f"/{base_path.strip('/')}/"


def pages_url(path: str, base_path: str) -> str:
    if path.startswith("/static/"):
        return f"{base_path}static/{quote(path.removeprefix('/static/'), safe='/')}"

    target = INTERNAL_PATHS.get(path.rstrip("/") or "/")
    if target is not None:
        return f"{base_path}{target}"

    if path.startswith("/"):
        return f"{base_path}{path.lstrip('/')}"

    return path


def rewrite_internal_links(html: str, base_path: str) -> str:
    def replace(match: re.Match[str]) -> str:
        attr, url = match.groups()
        if not url.startswith("/"):
            return match.group(0)
        return f'{attr}="{pages_url(url, base_path)}"'

    return re.sub(r'(href|src|action)="([^"]+)"', replace, html)


def seed_demo_data(user_id: int) -> None:
    today = date.today()
    workouts = [
        (today - timedelta(days=2), 52, 7, "Strength + zone 2 finisher"),
        (today - timedelta(days=5), 38, 6, "Tempo intervals and mobility"),
        (today - timedelta(days=9), 64, 8, "Lower body strength focus"),
        (today - timedelta(days=13), 35, 5, "Recovery ride"),
        (today - timedelta(days=18), 47, 7, "Upper body hypertrophy"),
        (today - timedelta(days=24), 58, 8, "Long aerobic session"),
        (today - timedelta(days=31), 42, 6, "Full body circuit"),
        (today - timedelta(days=39), 55, 7, "Hill repeats"),
    ]
    sleep_logs = [
        (today - timedelta(days=1), 7.4, 8, "Felt rested before training."),
        (today - timedelta(days=2), 6.8, 7, "Slightly restless but recovered."),
        (today - timedelta(days=3), 7.1, 8, "Good sleep consistency."),
        (today - timedelta(days=4), 6.2, 6, "Keep intensity moderate."),
        (today - timedelta(days=5), 7.8, 9, "Strong readiness signal."),
    ]
    now = datetime.now(UTC).isoformat()

    with db.get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM workout_sessions WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM sleep_logs WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM training_blocks WHERE user_id = ?", (user_id,))
        cur.execute(
            """
            UPDATE user_profiles
            SET age = ?, gender = ?, height_cm = ?, weight_kg = ?, bmi = ?, resting_heart_rate = ?
            WHERE user_id = ?
            """,
            (29, "F", 168, 64, 22.7, 58, user_id),
        )
        cur.execute(
            """
            UPDATE user_goals
            SET weekly_minutes_goal = ?, weekly_sessions_goal = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (180, 4, now, user_id),
        )
        for workout_date, duration, intensity, notes in workouts:
            cur.execute(
                """
                INSERT INTO workout_sessions
                (user_id, workout_date, total_duration_minutes, perceived_intensity, source, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, workout_date.isoformat(), duration, intensity, "manual", notes),
            )
        for sleep_date, hours, recovery, notes in sleep_logs:
            cur.execute(
                """
                INSERT INTO sleep_logs
                (user_id, sleep_date, sleep_hours, recovery_rating, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, sleep_date.isoformat(), hours, recovery, notes, now, now),
            )
        cur.execute(
            """
            INSERT INTO training_blocks
            (user_id, block_name, training_focus, start_date, end_date,
             target_weekly_minutes, target_weekly_sessions, target_effort,
             notes, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                "Spring strength base",
                "strength",
                (today - timedelta(days=21)).isoformat(),
                (today + timedelta(days=21)).isoformat(),
                180,
                4,
                7,
                "Build repeatable strength sessions while maintaining aerobic volume.",
                "active",
                now,
                now,
            ),
        )


def render_route(client, route: str, output_file: Path, base_path: str, user_id: int | None) -> None:
    with client.session_transaction() as session:
        session.clear()
        if user_id is not None:
            session["user_id"] = user_id

    response = client.get(route, follow_redirects=True)
    if response.status_code >= 400:
        raise RuntimeError(f"Failed to render {route}: HTTP {response.status_code}")
    html = response.get_data(as_text=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(rewrite_internal_links(html, base_path), encoding="utf-8")


def export(output_dir: Path, base_path: str) -> None:
    base_path = normalize_base_path(base_path)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "fitfuture-static.db"
        config.DB_PATH = db_path
        db.DB_PATH = db_path

        app = create_app({"TESTING": True, "SERVER_NAME": "fitfuture.local"})
        demo_user = db.fetch_one("SELECT user_id FROM users WHERE email = ?", (config.DEMO_USER_EMAIL,))
        if demo_user is None:
            raise RuntimeError("Demo user was not created during app initialization.")
        user_id = int(demo_user["user_id"])
        seed_demo_data(user_id)

        with app.test_client() as client:
            for route, filename, requires_user in STATIC_ROUTES:
                render_route(
                    client,
                    route,
                    output_dir / filename,
                    base_path,
                    user_id if requires_user else None,
                )

    shutil.copytree(ROOT / "static", output_dir / "static", dirs_exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export FitFuture as a static demo site.")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--base-path",
        default=os.environ.get("FITFUTURE_BASE_PATH", "/"),
        help="Base URL path for static links, such as /FitFuture/ for GitHub Pages.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export(args.output, args.base_path)
    print(f"Exported static FitFuture demo to {args.output}")

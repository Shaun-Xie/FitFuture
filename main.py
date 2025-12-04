from flask import Flask, request, redirect, url_for, render_template_string
import sqlite3
from datetime import datetime, date, timedelta
import os

import pandas as pd  # for Kaggle datasets

DB_PATH = "fitfuture.db"
app = Flask(__name__)

# Cached external data
EXTERNAL_STATS = {}
DATAFRAMES = {}


# ---------- DATABASE SETUP ----------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Basic users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            email          TEXT NOT NULL UNIQUE,
            password_hash  TEXT,
            created_at     TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'ACTIVE'
        );
    """)

    # Simple profile: age + gender (for cohort comparisons)
    cur.execute("""
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
    """)

    # Workouts (CRUD + filter)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workout_sessions (
            workout_id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id                INTEGER NOT NULL,
            workout_date           TEXT NOT NULL,   -- YYYY-MM-DD
            start_time             TEXT,            -- HH:MM
            end_time               TEXT,            -- HH:MM
            total_duration_minutes INTEGER,
            perceived_intensity    INTEGER,         -- 1..10
            source                 TEXT,            -- manual/app/device
            notes                  TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    """)

    # Seed one user + profile if missing (user_id = 1)
    cur.execute("SELECT COUNT(*) AS c FROM users;")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at, status) "
            "VALUES (?, ?, ?, ?);",
            ("test@example.com", "dummyhash", datetime.utcnow().isoformat(), "ACTIVE"),
        )

    cur.execute("SELECT COUNT(*) AS c FROM user_profiles WHERE user_id = 1;")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO user_profiles (user_id, age, gender, height_cm, weight_kg, bmi, resting_heart_rate) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, 22, "M", None, None, None, None),
        )

    conn.commit()
    conn.close()


# ---------- EXTERNAL CSV DATA (KAGGLE DATASETS) ----------

def compute_external_stats():
    """
    Load and cache small summary stats for the Kaggle datasets.
    Also stores full DataFrames in DATAFRAMES for analytics.
    """
    global EXTERNAL_STATS, DATAFRAMES
    if EXTERNAL_STATS:
        return EXTERNAL_STATS

    base = os.path.dirname(os.path.abspath(__file__))
    stats = {}

    datasets = [
        ("gym_members_exercise_tracking.csv", "gym", "Gym Members Exercise Tracking"),
        ("health_fitness_tracking_365days.csv", "hf365", "Health Fitness Tracking 365 Days"),
    ]

    for filename, key, label in datasets:
        path = os.path.join(base, filename)
        entry = {"name": label, "exists": False}
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                DATAFRAMES[key] = df
                entry["exists"] = True
                entry["num_rows"] = int(len(df))
                entry["num_cols"] = int(len(df.columns))

                # Gym dataset: durations and calories
                if key == "gym":
                    if "Calories_Burned" in df.columns:
                        entry["avg_calories_burned"] = float(df["Calories_Burned"].mean())
                    if "Session_Duration (hours)" in df.columns:
                        entry["avg_session_hours"] = float(df["Session_Duration (hours)"].mean())

                # 365-day dataset: steps, sleep, exercise
                if key == "hf365":
                    if "steps" in df.columns:
                        entry["avg_steps"] = float(df["steps"].mean())
                    if "sleep_hours" in df.columns:
                        entry["avg_sleep_hours"] = float(df["sleep_hours"].mean())
                    if "exercise_minutes" in df.columns:
                        entry["avg_exercise_minutes"] = float(df["exercise_minutes"].mean())

            except Exception as e:
                entry["error"] = str(e)
        stats[key] = entry

    EXTERNAL_STATS = stats
    return EXTERNAL_STATS


# ---------- USER PROFILE + ANALYTICS HELPERS ----------

def get_user_profile(user_id=1):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_profiles WHERE user_id = ?;", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def percentile_rank(series, value):
    """Return percentile rank of value within a numeric iterable."""
    if series is None or len(series) == 0:
        return None
    clean = [float(x) for x in series if pd.notnull(x)]
    if not clean:
        return None
    count = sum(1 for x in clean if x <= value)
    return 100.0 * count / len(clean)


def compute_fitness_summary(user_id=1):
    """
    Uses:
      - recent workouts (last 30 days) from workout_sessions
      - user profile (age, gender)
      - Kaggle datasets in DATAFRAMES

    Returns a dict with:
      - weekly_minutes, avg_duration, current_score, projected_score
      - hf365_percentile (daily exercise vs population)
      - gym_percentile (session duration vs gym population)
      - cohort_label, age, gender_label, etc.
    """
    profile = get_user_profile(user_id)
    result = {}

    # Recent workouts (last 30 days)
    conn = get_db()
    cur = conn.cursor()
    today = date.today()
    window_start = today - timedelta(days=30)
    cur.execute(
        """
        SELECT workout_date, total_duration_minutes
        FROM workout_sessions
        WHERE user_id = ?
          AND workout_date IS NOT NULL
          AND workout_date >= ?
          AND total_duration_minutes IS NOT NULL;
        """,
        (user_id, window_start.isoformat()),
    )
    rows = cur.fetchall()
    conn.close()

    if rows:
        durations = []
        dates = []
        for r in rows:
            durations.append(r["total_duration_minutes"])
            try:
                d = datetime.fromisoformat(r["workout_date"]).date()
            except Exception:
                try:
                    d = datetime.strptime(r["workout_date"], "%Y-%m-%d").date()
                except Exception:
                    continue
            dates.append(d)

        if durations:
            total_minutes = sum(durations)
            avg_duration = total_minutes / len(durations)

            if dates:
                span_days = (max(dates) - min(dates)).days + 1
            else:
                span_days = 1
            span_days = max(span_days, 1)

            # Approximate weekly volume from last 30 days
            weekly_minutes = total_minutes * 7.0 / span_days

            # Simple "fitness score": 30 min/week ~ 1 point, capped at 10
            current_score = min(10.0, weekly_minutes / 30.0)
            projected_score = min(10.0, current_score + 1.0)  # naive future bump

            result.update(
                {
                    "has_data": True,
                    "total_minutes_30d": total_minutes,
                    "avg_duration": avg_duration,
                    "weekly_minutes": weekly_minutes,
                    "current_score": current_score,
                    "projected_score": projected_score,
                }
            )
        else:
            result["has_data"] = False
    else:
        result["has_data"] = False

    # Make sure external datasets are loaded
    compute_external_stats()

    # Cohort info based on age & gender
    result["cohort_label"] = None
    result["hf365_percentile"] = None
    result["gym_percentile"] = None
    result["age"] = profile.get("age") if profile else None

    gender = (profile.get("gender") if profile else None) or ""
    gender_code = gender[0].upper() if gender else None
    result["gender_label"] = {"M": "males", "F": "females"}.get(gender_code, "users")

    weekly_minutes = result.get("weekly_minutes")
    if profile and profile.get("age") and gender_code and weekly_minutes:
        age = profile["age"]
        result["cohort_label"] = f"{age-2}–{age+2}yo {result['gender_label']}"

        # 1) 365-day dataset: daily exercise minutes
        df_hf = DATAFRAMES.get("hf365")
        if df_hf is not None and "exercise_minutes" in df_hf.columns:
            cohort = df_hf[
                (df_hf["age"].between(age - 2, age + 2))
                & (df_hf["gender"].astype(str).str.upper().str[0] == gender_code)
            ]
            if not cohort.empty:
                daily_equiv = weekly_minutes / 7.0
                pct = percentile_rank(cohort["exercise_minutes"], daily_equiv)
                result["hf365_percentile"] = pct
                result["hf365_cohort_size"] = len(cohort)

        # 2) Gym members dataset: session duration
        df_gym = DATAFRAMES.get("gym")
        if df_gym is not None and "Session_Duration (hours)" in df_gym.columns:
            cohort2 = df_gym[
                (df_gym["Age"].between(age - 2, age + 2))
                & (df_gym["Gender"].astype(str).str.upper().str[0] == gender_code)
            ]
            if not cohort2.empty and result.get("avg_duration"):
                session_minutes = cohort2["Session_Duration (hours)"] * 60.0
                pct2 = percentile_rank(session_minutes, result["avg_duration"])
                result["gym_percentile"] = pct2
                result["gym_cohort_size"] = len(cohort2)

    return result


# ---------- HTML TEMPLATE (MODERN UI + ANALYTICS) ----------

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>FitFuture Tracker</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --bg: #050816;
            --bg-elevated: #0b1020;
            --bg-soft: #12182b;
            --accent: #4f46e5;
            --accent-soft: rgba(79, 70, 229, 0.15);
            --accent-strong: #818cf8;
            --danger: #ef4444;
            --text-main: #e5e7eb;
            --text-muted: #9ca3af;
            --border-subtle: #1f2933;
            --radius-lg: 14px;
            --shadow-soft: 0 18px 45px rgba(0,0,0,0.45);
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text",
                         "Segoe UI", sans-serif;
            background: radial-gradient(circle at top left, #111827 0, #020617 45%, #000 100%);
            color: var(--text-main);
        }

        a { color: var(--accent-strong); text-decoration: none; }
        a:hover { text-decoration: underline; }

        .shell {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        header {
            background: radial-gradient(circle at top left, #1f2937, #020617);
            border-bottom: 1px solid rgba(148, 163, 184, 0.2);
            padding: 20px 16px;
        }

        .header-inner {
            max-width: 1100px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-logo {
            width: 36px;
            height: 36px;
            border-radius: 12px;
            background: conic-gradient(from 180deg, #38bdf8, #4f46e5, #ec4899, #22c55e, #38bdf8);
            padding: 2px;
        }

        .brand-logo-inner {
            width: 100%;
            height: 100%;
            border-radius: 10px;
            background: #020617;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-weight: 700;
            color: #e5e7eb;
        }

        .brand-text { display: flex; flex-direction: column; }

        .brand-title {
            font-weight: 600;
            letter-spacing: 0.02em;
        }

        .brand-subtitle {
            font-size: 12px;
            color: var(--text-muted);
        }

        .header-tag {
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            color: var(--text-muted);
            background: rgba(15,23,42,0.8);
        }

        main {
            flex: 1;
            padding: 24px 12px 40px;
        }

        .main-inner {
            max-width: 1100px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
            gap: 24px;
        }

        @media (max-width: 960px) {
            .main-inner {
                grid-template-columns: minmax(0, 1fr);
            }
        }

        .card {
            background: linear-gradient(145deg, var(--bg-soft), #050816);
            border-radius: var(--radius-lg);
            border: 1px solid rgba(55, 65, 81, 0.7);
            box-shadow: var(--shadow-soft);
            padding: 18px 18px 16px;
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: "";
            position: absolute;
            inset: -40%;
            background: radial-gradient(circle at top left,
                        rgba(79, 70, 229, 0.16), transparent 60%);
            opacity: 0.8;
            pointer-events: none;
        }

        .card-inner {
            position: relative;
            z-index: 1;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 10px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
        }

        .card-subtitle {
            font-size: 12px;
            color: var(--text-muted);
        }

        .pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 999px;
            background: var(--accent-soft);
            color: var(--accent-strong);
        }

        .pill-dot {
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: #22c55e;
        }

        form { margin: 0; }

        .field-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px 12px;
            margin-bottom: 10px;
        }

        .field {
            flex: 1 1 160px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .field label {
            font-size: 12px;
            color: var(--text-muted);
        }

        .field input,
        .field select,
        .field textarea {
            border-radius: 10px;
            border: 1px solid var(--border-subtle);
            background: rgba(15,23,42,0.9);
            padding: 7px 10px;
            color: var(--text-main);
            font-size: 13px;
            outline: none;
        }

        .field input:focus,
        .field select:focus,
        .field textarea:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 1px rgba(79, 70, 229, 0.5);
        }

        .field textarea {
            resize: vertical;
            min-height: 60px;
        }

        .btn-row {
            display: flex;
            gap: 8px;
            margin-top: 4px;
        }

        .btn {
            border-radius: 999px;
            border: none;
            padding: 7px 14px;
            font-size: 13px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent), #6366f1);
            color: #e5e7eb;
            box-shadow: 0 10px 25px rgba(79,70,229,0.45);
        }

        .btn-primary:hover { filter: brightness(1.05); }

        .btn-ghost {
            background: transparent;
            border: 1px solid rgba(148, 163, 184, 0.3);
            color: var(--text-muted);
        }

        .btn-ghost:hover {
            border-color: var(--accent-strong);
            color: var(--accent-strong);
        }

        .btn-danger {
            background: rgba(239, 68, 68, 0.1);
            color: #fecaca;
            border-radius: 999px;
            border: 1px solid rgba(248, 113, 113, 0.4);
        }

        .btn-danger:hover { background: rgba(239, 68, 68, 0.18); }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        thead { background: rgba(15, 23, 42, 0.96); }

        th, td {
            padding: 7px 9px;
            border-bottom: 1px solid rgba(31, 41, 55, 0.8);
        }

        th {
            text-align: left;
            font-weight: 500;
            color: var(--text-muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        tbody tr:hover { background: rgba(15, 23, 42, 0.8); }

        .badge-intensity {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 999px;
            background: rgba(248, 250, 252, 0.06);
            font-size: 11px;
            color: #e5e7eb;
        }

        .badge-intensity span {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 999px;
            margin-right: 5px;
        }

        .badge-intensity-low span { background: #22c55e; }
        .badge-intensity-mid span { background: #eab308; }
        .badge-intensity-high span { background: #f97316; }
        .badge-intensity-max span { background: #ef4444; }

        .chip-src {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 7px;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            font-size: 11px;
            color: var(--text-muted);
        }

        .chip-src-dot {
            width: 6px;
            height: 6px;
            border-radius: 999px;
            background: #38bdf8;
        }

        .actions-cell { display: flex; gap: 6px; }
        .actions-cell form { margin: 0; }

        .muted { color: var(--text-muted); }

        .pill-small {
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            color: var(--text-muted);
        }

        /* External stats UI */
        .external-stats { margin-top: 18px; }

        .external-cards {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }

        .external-card {
            flex: 1 1 180px;
            border-radius: 12px;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(55, 65, 81, 0.7);
            padding: 8px 10px;
            font-size: 12px;
        }

        .external-card-title {
            font-weight: 500;
            margin-bottom: 4px;
        }

        .external-card-metric {
            font-size: 11px;
            color: var(--text-muted);
        }

    </style>
</head>
<body>
<div class="shell">
    <header>
        <div class="header-inner">
            <div class="brand">
                <div class="brand-logo">
                    <div class="brand-logo-inner">FF</div>
                </div>
                <div class="brand-text">
                    <div class="brand-title">FitFuture Tracker</div>
                    <div class="brand-subtitle">
                        Workout log · Population comparisons · Simple projections
                    </div>
                </div>
            </div>
            <div class="header-tag">
                Checkpoint #2 · CRUD + Filter + Kaggle integration
            </div>
        </div>
    </header>

    <main>

        <!-- Profile card: age + gender for cohort-based comparisons -->
        <div style="max-width:1100px;margin:0 auto 16px auto;">
            <div class="card">
                <div class="card-inner">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Your profile for comparisons</div>
                            <div class="card-subtitle">
                                Age and gender are used to pick your comparison group in the population datasets.
                            </div>
                        </div>
                    </div>
                    <form method="post" action="{{ url_for('update_profile') }}">
                        <div class="field-row">
                            <div class="field">
                                <label for="age">Age</label>
                                <input type="number" id="age" name="age" min="10" max="90"
                                       value="{{ profile.age if profile else '' }}">
                            </div>
                            <div class="field">
                                <label for="gender">Gender</label>
                                <select id="gender" name="gender">
                                    {% set g = profile.gender if profile else '' %}
                                    <option value="" {% if not g %}selected{% endif %}>Not set</option>
                                    <option value="M" {% if g == 'M' %}selected{% endif %}>Male</option>
                                    <option value="F" {% if g == 'F' %}selected{% endif %}>Female</option>
                                </select>
                            </div>
                        </div>
                        <div class="btn-row">
                            <button type="submit" class="btn btn-ghost">Save profile</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div class="main-inner">

            <!-- LEFT: TABLE (READ + FILTER + EXTERNAL + ANALYTICS) -->
            <div class="card">
                <div class="card-inner">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Workout Sessions</div>
                            <div class="card-subtitle">
                                Log your workouts, filter by date and intensity, and see how you stack up.
                            </div>
                        </div>
                        <div class="pill">
                            <span class="pill-dot"></span>
                            {{ workouts|length }} session{{ '' if workouts|length == 1 else 's' }}
                        </div>
                    </div>

                    <!-- Filter -->
                    <form method="get" action="{{ url_for('index') }}">
                        <div class="field-row">
                            <div class="field">
                                <label for="min_date">Min date</label>
                                <input type="date" id="min_date" name="min_date"
                                       value="{{ request.args.get('min_date', '') }}">
                            </div>
                            <div class="field">
                                <label for="max_date">Max date</label>
                                <input type="date" id="max_date" name="max_date"
                                       value="{{ request.args.get('max_date', '') }}">
                            </div>
                            <div class="field">
                                <label for="min_intensity">Min intensity (1–10)</label>
                                <input type="number" id="min_intensity" name="min_intensity"
                                       min="1" max="10"
                                       value="{{ request.args.get('min_intensity', '') }}">
                            </div>
                        </div>
                        <div class="btn-row">
                            <button type="submit" class="btn btn-ghost">Apply filters</button>
                            <a class="btn btn-ghost" href="{{ url_for('index') }}">Clear</a>
                        </div>
                    </form>

                    <!-- Table -->
                    <div style="margin-top: 18px; overflow-x:auto;">
                        <table>
                            <thead>
                            <tr>
                                <th>ID</th>
                                <th>User</th>
                                <th>Date</th>
                                <th>Duration</th>
                                <th>Intensity</th>
                                <th>Source</th>
                                <th>Notes</th>
                                <th></th>
                            </tr>
                            </thead>
                            <tbody>
                            {% for w in workouts %}
                                {% set intensity = w.perceived_intensity or 0 %}
                                {% if intensity >= 9 %}
                                    {% set intensity_class = 'badge-intensity badge-intensity-max' %}
                                {% elif intensity >= 7 %}
                                    {% set intensity_class = 'badge-intensity badge-intensity-high' %}
                                {% elif intensity >= 4 %}
                                    {% set intensity_class = 'badge-intensity badge-intensity-mid' %}
                                {% elif intensity >= 1 %}
                                    {% set intensity_class = 'badge-intensity badge-intensity-low' %}
                                {% else %}
                                    {% set intensity_class = 'muted' %}
                                {% endif %}

                                <tr>
                                    <td>#{{ w.workout_id }}</td>
                                    <td>{{ w.user_id }}</td>
                                    <td>{{ w.workout_date }}</td>
                                    <td>
                                        {% if w.total_duration_minutes %}
                                            {{ w.total_duration_minutes }} min
                                        {% else %}
                                            <span class="muted">—</span>
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if w.perceived_intensity %}
                                            <span class="{{ intensity_class }}">
                                                <span></span>
                                                {{ w.perceived_intensity }}/10
                                            </span>
                                        {% else %}
                                            <span class="muted">—</span>
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if w.source %}
                                            <span class="chip-src">
                                                <span class="chip-src-dot"></span>{{ w.source }}
                                            </span>
                                        {% else %}
                                            <span class="pill-small">unspecified</span>
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if w.notes %}
                                            {{ w.notes }}
                                        {% else %}
                                            <span class="muted">No notes</span>
                                        {% endif %}
                                    </td>
                                    <td>
                                        <div class="actions-cell">
                                            <a class="btn btn-ghost"
                                               style="padding:3px 10px;font-size:12px;"
                                               href="{{ url_for('edit_workout', workout_id=w.workout_id) }}">
                                                Edit
                                            </a>
                                            <form method="post"
                                                  action="{{ url_for('delete_workout', workout_id=w.workout_id) }}"
                                                  onsubmit="return confirm('Delete this workout?');">
                                                <button type="submit"
                                                    class="btn btn-danger"
                                                    style="padding:3px 10px;font-size:12px;">
                                                    Delete
                                                </button>
                                            </form>
                                        </div>
                                    </td>
                                </tr>
                            {% endfor %}
                            {% if workouts|length == 0 %}
                                <tr>
                                    <td colspan="8" class="muted">
                                        No workouts yet. Use the form on the right to add one.
                                    </td>
                                </tr>
                            {% endif %}
                            </tbody>
                        </table>
                    </div>

                    <!-- External datasets snapshot (Kaggle) -->
                    {% if external_stats %}
                    <div class="external-stats">
                        <div class="card-subtitle" style="margin-bottom:6px;">
                            Population snapshot from Kaggle datasets:
                        </div>
                        <div class="external-cards">
                            {% for key, ds in external_stats.items() %}
                                {% if ds.exists %}
                                <div class="external-card">
                                    <div class="external-card-title">{{ ds.name }}</div>
                                    <div class="external-card-metric">
                                        {{ ds.num_rows }} rows · {{ ds.num_cols }} columns
                                    </div>
                                    {% if ds.avg_calories_burned is defined %}
                                        <div class="external-card-metric">
                                            Avg calories: {{ ds.avg_calories_burned|round(1) }}
                                        </div>
                                    {% endif %}
                                    {% if ds.avg_session_hours is defined %}
                                        <div class="external-card-metric">
                                            Avg session: {{ ds.avg_session_hours|round(2) }} hours
                                        </div>
                                    {% endif %}
                                    {% if ds.avg_steps is defined %}
                                        <div class="external-card-metric">
                                            Avg steps/day: {{ ds.avg_steps|round(0) }}
                                        </div>
                                    {% endif %}
                                    {% if ds.avg_sleep_hours is defined %}
                                        <div class="external-card-metric">
                                            Avg sleep: {{ ds.avg_sleep_hours|round(2) }} hours
                                        </div>
                                    {% endif %}
                                    {% if ds.avg_exercise_minutes is defined %}
                                        <div class="external-card-metric">
                                            Avg exercise: {{ ds.avg_exercise_minutes|round(1) }} min/day
                                        </div>
                                    {% endif %}
                                    {% if ds.error is defined %}
                                        <div class="external-card-metric" style="color:#fecaca;">
                                            Error loading: {{ ds.error }}
                                        </div>
                                    {% endif %}
                                </div>
                                {% endif %}
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}

                    <!-- Your training vs population + projection -->
                    {% if fitness_summary and fitness_summary.has_data %}
                    <div class="external-stats">
                        <div class="card-subtitle" style="margin-bottom:6px;">
                            Your training vs population
                        </div>
                        <div class="external-cards">
                            <div class="external-card">
                                <div class="external-card-title">Your recent training</div>
                                <div class="external-card-metric">
                                    ~{{ fitness_summary.weekly_minutes|round(1) }} min/week (last 30 days)
                                </div>
                                <div class="external-card-metric">
                                    Avg session: {{ fitness_summary.avg_duration|round(1) }} min
                                </div>
                                {% if fitness_summary.cohort_label %}
                                <div class="external-card-metric">
                                    Comparison group: {{ fitness_summary.cohort_label }}
                                </div>
                                {% endif %}
                            </div>
                            <div class="external-card">
                                <div class="external-card-title">Population percentiles</div>
                                {% if fitness_summary.hf365_percentile %}
                                  <div class="external-card-metric">
                                      Daily exercise vs 365-day dataset:
                                      ~{{ fitness_summary.hf365_percentile|round(0) }}th percentile
                                  </div>
                                {% endif %}
                                {% if fitness_summary.gym_percentile %}
                                  <div class="external-card-metric">
                                      Session duration vs gym dataset:
                                      ~{{ fitness_summary.gym_percentile|round(0) }}th percentile
                                  </div>
                                {% endif %}
                                {% if not fitness_summary.hf365_percentile and not fitness_summary.gym_percentile %}
                                  <div class="external-card-metric">
                                      Not enough data yet to compute percentiles.
                                  </div>
                                {% endif %}
                            </div>
                            <div class="external-card">
                                <div class="external-card-title">Simple projection</div>
                                <div class="external-card-metric">
                                    Current fitness score: {{ fitness_summary.current_score|round(1) }}/10
                                </div>
                                <div class="external-card-metric">
                                    Projected in 3 months (if you keep this pace):
                                    {{ fitness_summary.projected_score|round(1) }}/10
                                </div>
                            </div>
                        </div>
                    </div>
                    {% elif fitness_summary and not fitness_summary.has_data %}
                    <div class="external-stats">
                        <div class="card-subtitle">
                            Log a few workouts to see your population comparison and projections.
                        </div>
                    </div>
                    {% endif %}

                </div>
            </div>

            <!-- RIGHT: FORM (CREATE / UPDATE) -->
            <div class="card">
                <div class="card-inner">
                    <div class="card-header">
                        <div>
                            <div class="card-title">
                                {{ 'Edit workout' if workout else 'Log a new workout' }}
                            </div>
                            <div class="card-subtitle">
                                Capture what you did so we can track your progress and compare you to similar athletes.
                            </div>
                        </div>
                    </div>

                    <form method="post" action="{{ form_action }}">
                        <div class="field-row">
                            <div class="field">
                                <label for="user_id">User ID</label>
                                <input type="number" id="user_id" name="user_id"
                                       value="{{ workout.user_id if workout else 1 }}" required>
                            </div>
                            <div class="field">
                                <label for="workout_date">Workout date</label>
                                <input type="date" id="workout_date" name="workout_date"
                                       value="{{ workout.workout_date if workout else '' }}" required>
                            </div>
                        </div>

                        <div class="field-row">
                            <div class="field">
                                <label for="start_time">Start time</label>
                                <input type="time" id="start_time" name="start_time"
                                       value="{{ workout.start_time if workout else '' }}">
                            </div>
                            <div class="field">
                                <label for="end_time">End time</label>
                                <input type="time" id="end_time" name="end_time"
                                       value="{{ workout.end_time if workout else '' }}">
                            </div>
                        </div>

                        <div class="field-row">
                            <div class="field">
                                <label for="total_duration_minutes">Duration (minutes)</label>
                                <input type="number" id="total_duration_minutes"
                                       name="total_duration_minutes" min="0"
                                       value="{{ workout.total_duration_minutes if workout else '' }}">
                            </div>
                            <div class="field">
                                <label for="perceived_intensity">Intensity (1–10)</label>
                                <input type="number" id="perceived_intensity"
                                       name="perceived_intensity" min="1" max="10"
                                       value="{{ workout.perceived_intensity if workout else '' }}">
                            </div>
                        </div>

                        <div class="field-row">
                            <div class="field">
                                <label for="source">Source</label>
                                <select id="source" name="source">
                                    {% set src = workout.source if workout else '' %}
                                    <option value="" {% if not src %}selected{% endif %}>Not specified</option>
                                    <option value="manual" {% if src == 'manual' %}selected{% endif %}>Manual</option>
                                    <option value="app" {% if src == 'app' %}selected{% endif %}>App</option>
                                    <option value="device" {% if src == 'device' %}selected{% endif %}>Device</option>
                                </select>
                            </div>
                        </div>

                        <div class="field-row">
                            <div class="field" style="flex:1 1 100%;">
                                <label for="notes">Notes</label>
                                <textarea id="notes" name="notes" rows="3"
                                          placeholder="Optional details: how you felt, PRs, etc.">{{ workout.notes if workout else '' }}</textarea>
                            </div>
                        </div>

                        <div class="btn-row">
                            <button type="submit" class="btn btn-primary">
                                {{ 'Update workout' if workout else 'Create workout' }}
                            </button>
                            {% if workout %}
                                <a href="{{ url_for('index') }}" class="btn btn-ghost">Cancel edit</a>
                            {% endif %}
                        </div>
                    </form>
                </div>
            </div>

        </div>
    </main>
</div>
</body>
</html>
"""


# ---------- ROUTES (CRUD + FILTER + PROFILE) ----------

@app.route("/", methods=["GET"])
def index():
    conn = get_db()
    cur = conn.cursor()

    query = "SELECT * FROM workout_sessions WHERE 1=1"
    params = []

    min_date = request.args.get("min_date")
    max_date = request.args.get("max_date")
    min_intensity = request.args.get("min_intensity")

    if min_date:
        query += " AND workout_date >= ?"
        params.append(min_date)
    if max_date:
        query += " AND workout_date <= ?"
        params.append(max_date)
    if min_intensity:
        query += " AND (perceived_intensity IS NOT NULL AND perceived_intensity >= ?)"
        params.append(int(min_intensity))

    query += " ORDER BY workout_date DESC, workout_id DESC"

    cur.execute(query, params)
    workouts = cur.fetchall()
    conn.close()

    external_stats = compute_external_stats()
    profile = get_user_profile(1)
    fitness_summary = compute_fitness_summary(1)

    return render_template_string(
        BASE_TEMPLATE,
        workouts=workouts,
        workout=None,
        form_action=url_for("create_workout"),
        external_stats=external_stats,
        profile=profile,
        fitness_summary=fitness_summary,
    )


@app.route("/workouts", methods=["POST"])
def create_workout():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO workout_sessions
        (user_id, workout_date, start_time, end_time,
         total_duration_minutes, perceived_intensity, source, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form.get("user_id"),
        request.form.get("workout_date"),
        request.form.get("start_time") or None,
        request.form.get("end_time") or None,
        int(request.form.get("total_duration_minutes")) if request.form.get("total_duration_minutes") else None,
        int(request.form.get("perceived_intensity")) if request.form.get("perceived_intensity") else None,
        request.form.get("source") or None,
        request.form.get("notes") or None,
    ))

    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/workouts/<int:workout_id>/edit", methods=["GET"])
def edit_workout(workout_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM workout_sessions WHERE workout_id = ?;", (workout_id,))
    workout = cur.fetchone()

    cur.execute("SELECT * FROM workout_sessions ORDER BY workout_date DESC, workout_id DESC;")
    workouts = cur.fetchall()
    conn.close()

    external_stats = compute_external_stats()
    profile = get_user_profile(1)
    fitness_summary = compute_fitness_summary(1)

    return render_template_string(
        BASE_TEMPLATE,
        workouts=workouts,
        workout=workout,
        form_action=url_for("update_workout", workout_id=workout_id),
        external_stats=external_stats,
        profile=profile,
        fitness_summary=fitness_summary,
    )


@app.route("/workouts/<int:workout_id>", methods=["POST"])
def update_workout(workout_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE workout_sessions
        SET user_id = ?,
            workout_date = ?,
            start_time = ?,
            end_time = ?,
            total_duration_minutes = ?,
            perceived_intensity = ?,
            source = ?,
            notes = ?
        WHERE workout_id = ?
    """, (
        request.form.get("user_id"),
        request.form.get("workout_date"),
        request.form.get("start_time") or None,
        request.form.get("end_time") or None,
        int(request.form.get("total_duration_minutes")) if request.form.get("total_duration_minutes") else None,
        int(request.form.get("perceived_intensity")) if request.form.get("perceived_intensity") else None,
        request.form.get("source") or None,
        request.form.get("notes") or None,
        workout_id
    ))

    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/workouts/<int:workout_id>/delete", methods=["POST"])
def delete_workout(workout_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM workout_sessions WHERE workout_id = ?;", (workout_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/profile", methods=["POST"])
def update_profile():
    """Update age + gender for user_id = 1."""
    age_raw = request.form.get("age")
    gender = request.form.get("gender") or None

    age_val = None
    if age_raw:
        try:
            age_val = int(age_raw)
        except ValueError:
            age_val = None

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE user_profiles SET age = ?, gender = ? WHERE user_id = 1;",
        (age_val, gender),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


# ---------- MAIN ----------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

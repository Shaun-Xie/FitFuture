from flask import Flask, request, redirect, url_for, render_template_string
import sqlite3
from datetime import datetime, date, timedelta
import os
import pandas as pd

app = Flask(__name__)
DB_PATH = "fitfuture.db"

EXTERNAL_STATS = {}
DATAFRAMES = {}


# ===========================================================
# DATABASE SETUP
# ===========================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        );
    """)

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

    cur.execute("""
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
    """)

    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
            INSERT INTO users (email, password_hash, created_at, status)
            VALUES (?, ?, ?, ?)
        """, ("test@example.com", "hash", datetime.utcnow().isoformat(), "ACTIVE"))

    cur.execute("SELECT COUNT(*) AS c FROM user_profiles WHERE user_id = 1")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
            INSERT INTO user_profiles (user_id, age, gender)
            VALUES (?, ?, ?)
        """, (1, 22, "M"))

    conn.commit()
    conn.close()


# ===========================================================
# LOAD 3 DATASETS
# ===========================================================

def compute_external_stats():
    global EXTERNAL_STATS, DATAFRAMES
    if EXTERNAL_STATS:
        return EXTERNAL_STATS

    base = os.path.dirname(os.path.abspath(__file__))

    datasets = [
        ("gym_members_exercise_tracking.csv", "gym", "Gym Members Exercise Tracking"),
        ("health_fitness_tracking_365days.csv", "hf365", "Health Fitness Tracking 365 Days"),
        ("health_fitness_dataset.csv", "health", "General Health + Wellness Dataset")
    ]

    stats = {}

    for file, key, label in datasets:
        path = os.path.join(base, file)
        entry = {"name": label, "exists": False}

        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                DATAFRAMES[key] = df
                entry["exists"] = True
                entry["num_rows"] = len(df)
                entry["num_cols"] = len(df.columns)

                if key == "gym":
                    if "Session_Duration (hours)" in df:
                        entry["avg_session_hours"] = df["Session_Duration (hours)"].mean()

                if key == "hf365":
                    if "exercise_minutes" in df:
                        entry["avg_exercise_minutes"] = df["exercise_minutes"].mean()

                if key == "health":
                    if "resting_heart_rate" in df:
                        entry["avg_resting_hr"] = df["resting_heart_rate"].mean()
                    if "hours_sleep" in df:
                        entry["avg_sleep_hours"] = df["hours_sleep"].mean()

            except Exception as e:
                entry["error"] = str(e)

        stats[key] = entry

    EXTERNAL_STATS = stats
    return stats


# ===========================================================
# ANALYTICS HELPERS
# ===========================================================

def get_user_profile(user_id=1):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def percentile_rank(series, value):
    series = [float(x) for x in series if pd.notnull(x)]
    if not series:
        return None
    count = sum(1 for x in series if x <= value)
    return 100 * count / len(series)


def compute_fitness_summary(user_id=1):
    profile = get_user_profile(user_id)
    result = {}

    # Load last 30 days workouts
    conn = get_db()
    cur = conn.cursor()
    window = (date.today() - timedelta(days=30)).isoformat()

    cur.execute("""
        SELECT workout_date, total_duration_minutes
        FROM workout_sessions
        WHERE user_id = ? AND workout_date >= ? AND total_duration_minutes IS NOT NULL
    """, (user_id, window))

    rows = cur.fetchall()
    conn.close()

    if rows:
        durations = [r["total_duration_minutes"] for r in rows]
        total = sum(durations)
        avg = total / len(durations)

        dates = [datetime.fromisoformat(r["workout_date"]).date() for r in rows]
        span = max((max(dates) - min(dates)).days + 1, 1)

        weekly = total * 7 / span
        score = min(10, weekly / 30)
        proj = min(10, score + 1)

        result.update(
            has_data=True,
            total_minutes_30d=total,
            avg_duration=avg,
            weekly_minutes=weekly,
            current_score=score,
            projected_score=proj,
        )
    else:
        result["has_data"] = False

    compute_external_stats()

    age = profile.get("age")
    gender = profile.get("gender")

    if age and gender and result.get("weekly_minutes"):
        result["cohort_label"] = f"{age-2}–{age+2}yo {('males' if gender=='M' else 'females')}"

        # HF365 comparison
        df365 = DATAFRAMES.get("hf365")
        if df365 is not None:
            cohort = df365[
                (df365["age"].between(age-2, age+2)) &
                (df365["gender"].astype(str).str[0].str.upper() == gender)
            ]
            if not cohort.empty:
                daily_equiv = result["weekly_minutes"] / 7
                result["hf365_percentile"] = percentile_rank(
                    cohort["exercise_minutes"], daily_equiv
                )

        # Gym comparison
        df_gym = DATAFRAMES.get("gym")
        if df_gym is not None:
            cohort = df_gym[
                (df_gym["Age"].between(age-2, age+2)) &
                (df_gym["Gender"].astype(str).str[0].str.upper() == gender)
            ]

            if not cohort.empty and result.get("avg_duration"):
                mins = cohort["Session_Duration (hours)"] * 60
                result["gym_percentile"] = percentile_rank(mins, result["avg_duration"])

    return result


# HTML
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
            padding: 16px 16px 10px 16px;
        }

        .header-inner {
            max-width: 1100px;
            margin: 0 auto 8px auto;
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

        .nav-tabs {
            max-width: 1100px;
            margin: 0 auto;
            display: flex;
            gap: 8px;
            font-size: 13px;
        }

        .nav-tab {
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid transparent;
            color: var(--text-muted);
            cursor: pointer;
            text-decoration: none;
        }

        .nav-tab-active {
            border-color: rgba(148, 163, 184, 0.7);
            background: rgba(15,23,42,0.95);
            color: #e5e7eb;
        }

        .nav-tab:hover {
            border-color: rgba(148, 163, 184, 0.7);
        }

        main {
            flex: 1;
            padding: 20px 12px 40px;
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

        .analytics-grid {
            max-width: 1100px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
            gap: 20px;
        }

        @media (max-width: 960px) {
            .analytics-grid {
                grid-template-columns: minmax(0, 1fr);
            }
        }

        .chart-container {
            position: relative;
            width: 100%;
            height: 220px;
            margin-top: 6px;
        }

    </style>
    {% if active_view == 'analytics' %}
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    {% endif %}
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
        </div>
        <div class="nav-tabs">
            <a href="{{ url_for('index') }}"
               class="nav-tab {% if active_view == 'workouts' %}nav-tab-active{% endif %}">
                Workouts
            </a>
            <a href="{{ url_for('analytics') }}"
               class="nav-tab {% if active_view == 'analytics' %}nav-tab-active{% endif %}">
                Analytics
            </a>
        </div>
    </header>

    <main>

        {% if active_view == 'analytics' %}

        <!-- ANALYTICS VIEW -->
        <div class="analytics-grid">
            <div class="card">
                <div class="card-inner">
                    <div class="card-header">
                        <div>
                            <div class="card-title">You vs population</div>
                            <div class="card-subtitle">
                                Based on your last 30 days of training and your age/gender profile.
                            </div>
                        </div>
                    </div>
                    {% if fitness_summary and fitness_summary.has_data %}
                        <div class="external-cards">
                            <div class="external-card">
                                <div class="external-card-title">Your training snapshot</div>
                                <div class="external-card-metric">
                                    Weekly volume: ~{{ fitness_summary.weekly_minutes|round(1) }} min/week
                                </div>
                                <div class="external-card-metric">
                                    Avg session: {{ fitness_summary.avg_duration|round(1) }} min
                                </div>
                                {% if fitness_summary.cohort_label %}
                                <div class="external-card-metric">
                                    Comparison group: {{ fitness_summary.cohort_label }}
                                </div>
                                {% else %}
                                <div class="external-card-metric">
                                    Set your age & gender in the profile to enable cohort-based comparisons.
                                </div>
                                {% endif %}
                            </div>
                            <div class="external-card">
                                <div class="external-card-title">Percentile estimates</div>
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
                                      Not enough population data yet to compute percentiles.
                                  </div>
                                {% endif %}
                            </div>
                            <div class="external-card">
                                <div class="external-card-title">Projection</div>
                                <div class="external-card-metric">
                                    Current fitness score: {{ fitness_summary.current_score|round(1) }}/10
                                </div>
                                <div class="external-card-metric">
                                    Projected in 3 months (keep this pace):
                                    {{ fitness_summary.projected_score|round(1) }}/10
                                </div>
                                <div class="external-card-metric">
                                    This is a simple prototype projection based only on your recent volume.
                                </div>
                            </div>
                        </div>
                    {% else %}
                        <div class="card-subtitle">
                            Log a few workouts and set your age/gender in the Workouts tab to see comparisons here.
                        </div>
                    {% endif %}
                </div>
            </div>

            <div class="card">
                <div class="card-inner">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Population snapshot</div>
                            <div class="card-subtitle">
                                Aggregates from Kaggle datasets used as baselines.
                            </div>
                        </div>
                    </div>
                    {% if external_stats %}
                    <div class="external-cards">
                        {% for key, ds in external_stats.items() %}
                            {% if ds.exists %}
                            <div class="external-card">
                                <div class="external-card-title">{{ ds.name }}</div>
                                <div class="external-card-metric">
                                    {{ ds.num_rows }} rows · {{ ds.num_cols }} columns
                                </div>
                                {% if ds.avg_steps is defined %}
                                    <div class="external-card-metric">
                                        Avg steps/day: {{ ds.avg_steps|round(0) }}
                                    </div>
                                {% endif %}
                                {% if ds.avg_exercise_minutes is defined %}
                                    <div class="external-card-metric">
                                        Avg exercise: {{ ds.avg_exercise_minutes|round(1) }} min/day
                                    </div>
                                {% endif %}
                                {% if ds.avg_session_hours is defined %}
                                    <div class="external-card-metric">
                                        Avg gym session: {{ ds.avg_session_hours|round(2) }} hours
                                    </div>
                                {% endif %}
                            </div>
                            {% endif %}
                        {% endfor %}
                    </div>
                    {% else %}
                    <div class="card-subtitle">
                        No Kaggle CSVs detected in project folder.
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>

        <div style="max-width:1100px;margin:20px auto 0 auto;">
            <div class="card">
                <div class="card-inner">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Visual comparisons</div>
                            <div class="card-subtitle">
                                Simple charts comparing you vs population and your current vs projected score.
                            </div>
                        </div>
                    </div>
                    {% if fitness_summary and fitness_summary.has_data %}
                    <div class="field-row">
                        <div class="field">
                            <label>Exercise volume per day</label>
                            <div class="chart-container">
                                <canvas id="chartDailyExercise"></canvas>
                            </div>
                        </div>
                        <div class="field">
                            <label>Session duration</label>
                            <div class="chart-container">
                                <canvas id="chartSessionDuration"></canvas>
                            </div>
                        </div>
                    </div>
                    <div class="field-row">
                        <div class="field">
                            <label>Fitness score: now vs 3 months</label>
                            <div class="chart-container">
                                <canvas id="chartFitnessScore"></canvas>
                            </div>
                        </div>
                    </div>
                    {% else %}
                    <div class="card-subtitle">
                        Charts will appear once you have at least a few workouts in the last 30 days.
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>

        {% if fitness_summary and fitness_summary.has_data %}
        <script>
            const userDailyExercise = {{ user_daily_exercise|default('null') }};
            const popDailyExercise = {{ pop_daily_exercise|default('null') }};

            const userAvgDuration = {{ user_avg_duration|default('null') }};
            const popAvgDuration = {{ pop_avg_duration|default('null') }};

            const currentScore = {{ current_score|default('null') }};
            const projectedScore = {{ projected_score|default('null') }};

            function createBarChart(ctx, labels, userValue, popValue, labelUser, labelPop) {
                if (ctx === null || userValue === null || popValue === null) return;

                new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: labelUser,
                                data: [userValue],
                                backgroundColor: 'rgba(129, 140, 248, 0.85)'
                            },
                            {
                                label: labelPop,
                                data: [popValue],
                                backgroundColor: 'rgba(148, 163, 184, 0.85)'
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: {
                                    color: '#e5e7eb',
                                    font: { size: 11 }
                                }
                            }
                        },
                        scales: {
                            x: {
                                ticks: { color: '#9ca3af', font: { size: 11 } },
                                grid: { display: false }
                            },
                            y: {
                                ticks: { color: '#9ca3af', font: { size: 11 } },
                                grid: { color: 'rgba(55,65,81,0.7)' }
                            }
                        }
                    }
                });
            }

            function createScoreChart(ctx, currentValue, futureValue) {
                if (ctx === null || currentValue === null || futureValue === null) return;

                new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: ['Now', '3 months'],
                        datasets: [{
                            label: 'Fitness score (0–10)',
                            data: [currentValue, futureValue],
                            backgroundColor: ['rgba(96, 165, 250, 0.9)', 'rgba(52, 211, 153, 0.9)']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: {
                                    color: '#e5e7eb',
                                    font: { size: 11 }
                                }
                            }
                        },
                        scales: {
                            x: {
                                ticks: { color: '#9ca3af', font: { size: 11 } },
                                grid: { display: false }
                            },
                            y: {
                                suggestedMin: 0,
                                suggestedMax: 10,
                                ticks: { color: '#9ca3af', font: { size: 11 } },
                                grid: { color: 'rgba(55,65,81,0.7)' }
                            }
                        }
                    }
                });
            }

            window.addEventListener('load', () => {
                const ctxDaily = document.getElementById('chartDailyExercise')?.getContext('2d');
                const ctxSession = document.getElementById('chartSessionDuration')?.getContext('2d');
                const ctxScore = document.getElementById('chartFitnessScore')?.getContext('2d');

                createBarChart(
                    ctxDaily,
                    ['Exercise (min/day)'],
                    userDailyExercise,
                    popDailyExercise,
                    'You',
                    'Population avg'
                );

                createBarChart(
                    ctxSession,
                    ['Session duration (min)'],
                    userAvgDuration,
                    popAvgDuration,
                    'Your avg',
                    'Population avg'
                );

                createScoreChart(
                    ctxScore,
                    currentScore,
                    projectedScore
                );
            });
        </script>
        {% endif %}

        {% else %}

        <!-- WORKOUTS VIEW -->

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

            <!-- LEFT: TABLE -->
            <div class="card">
                <div class="card-inner">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Workout Sessions</div>
                            <div class="card-subtitle">
                                Log your workouts, filter by date and intensity.
                            </div>
                        </div>
                        <div class="pill">
                            <span class="pill-dot"></span>
                            {{ workouts|length }} session{{ '' if workouts|length == 1 else 's' }}
                        </div>
                    </div>

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
                </div>
            </div>

            <!-- RIGHT: FORM -->
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

        {% endif %}
    </main>
</div>
</body>
</html>
"""


# ===========================================================
# ROUTES
# ===========================================================

@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()

    query = "SELECT * FROM workout_sessions WHERE 1=1"
    params = []

    if request.args.get("min_date"):
        query += " AND workout_date >= ?"
        params.append(request.args["min_date"])

    if request.args.get("max_date"):
        query += " AND workout_date <= ?"
        params.append(request.args["max_date"])

    if request.args.get("min_intensity"):
        query += " AND perceived_intensity >= ?"
        params.append(int(request.args["min_intensity"]))

    query += " ORDER BY workout_date DESC, workout_id DESC"
    cur.execute(query, params)

    workouts = cur.fetchall()
    conn.close()

    return render_template_string(
        BASE_TEMPLATE,
        active_view="workouts",
        workouts=workouts,
        workout=None,
        form_action=url_for("create_workout"),
        external_stats=compute_external_stats(),
        profile=get_user_profile(1),
        fitness_summary=compute_fitness_summary(1),
        user_daily_exercise=None,
        pop_daily_exercise=None,
        user_avg_duration=None,
        pop_avg_duration=None,
        current_score=None,
        projected_score=None,
    )


@app.route("/analytics")
def analytics():
    ext = compute_external_stats()
    prof = get_user_profile(1)
    summ = compute_fitness_summary(1)

    daily = None
    avgdur = None
    cs = None
    ps = None
    pop_daily = None
    pop_duration = None

    if summ.get("has_data"):
        daily = summ["weekly_minutes"] / 7
        avgdur = summ["avg_duration"]
        cs = summ["current_score"]
        ps = summ["projected_score"]

    if ext.get("hf365", {}).get("avg_exercise_minutes") is not None:
        pop_daily = ext["hf365"]["avg_exercise_minutes"]

    if ext.get("gym", {}).get("avg_session_hours") is not None:
        pop_duration = ext["gym"]["avg_session_hours"] * 60

    return render_template_string(
        BASE_TEMPLATE,
        active_view="analytics",
        workouts=[],
        workout=None,
        form_action="",
        external_stats=ext,
        profile=prof,
        fitness_summary=summ,
        user_daily_exercise=daily,
        pop_daily_exercise=pop_daily,
        user_avg_duration=avgdur,
        pop_avg_duration=pop_duration,
        current_score=cs,
        projected_score=ps,
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
        request.form["user_id"],
        request.form["workout_date"],
        request.form.get("start_time"),
        request.form.get("end_time"),
        int(request.form["total_duration_minutes"]) if request.form.get("total_duration_minutes") else None,
        int(request.form["perceived_intensity"]) if request.form.get("perceived_intensity") else None,
        request.form.get("source"),
        request.form.get("notes"),
    ))

    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/workouts/<int:workout_id>/edit")
def edit_workout(workout_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM workout_sessions WHERE workout_id = ?", (workout_id,))
    workout = cur.fetchone()

    cur.execute("SELECT * FROM workout_sessions ORDER BY workout_date DESC")
    workouts = cur.fetchall()
    conn.close()

    return render_template_string(
        BASE_TEMPLATE,
        active_view="workouts",
        workouts=workouts,
        workout=workout,
        form_action=url_for("update_workout", workout_id=workout_id),
        external_stats=compute_external_stats(),
        profile=get_user_profile(1),
        fitness_summary=compute_fitness_summary(1),
        user_daily_exercise=None,
        pop_daily_exercise=None,
        user_avg_duration=None,
        pop_avg_duration=None,
        current_score=None,
        projected_score=None,
    )


@app.route("/workouts/<int:workout_id>", methods=["POST"])
def update_workout(workout_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE workout_sessions
        SET user_id=?, workout_date=?, start_time=?, end_time=?,
            total_duration_minutes=?, perceived_intensity=?,
            source=?, notes=?
        WHERE workout_id=?
    """, (
        request.form["user_id"],
        request.form["workout_date"],
        request.form.get("start_time"),
        request.form.get("end_time"),
        int(request.form["total_duration_minutes"]) if request.form.get("total_duration_minutes") else None,
        int(request.form["perceived_intensity"]) if request.form.get("perceived_intensity") else None,
        request.form.get("source"),
        request.form.get("notes"),
        workout_id
    ))

    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/workouts/<int:workout_id>/delete", methods=["POST"])
def delete_workout(workout_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM workout_sessions WHERE workout_id=?", (workout_id,))
    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/profile", methods=["POST"])
def update_profile():
    conn = get_db()
    cur = conn.cursor()

    age = request.form.get("age")
    gender = request.form.get("gender")

    cur.execute("""
        UPDATE user_profiles SET age=?, gender=? WHERE user_id=1
    """, (age, gender))

    conn.commit()
    conn.close()
    return redirect("/")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

# FitFuture

FitFuture is a Flask fitness intelligence dashboard that helps users log workouts, understand training consistency, and compare recent activity against public population datasets. The project is intentionally built as a portfolio-ready full-stack prototype: it combines CRUD workflows, SQLite persistence, data processing with pandas, Chart.js visualizations, and a polished responsive frontend.

## Product idea

Most simple workout trackers show what happened. FitFuture is designed to answer a more useful question:

> Am I training consistently enough, and how does my recent activity compare to similar people?

The app includes a demo user for quick exploration, while registration allows new users to create their own private workout history.

## Current features

- Login, logout, and registration with password hashing.
- Per-user workout ownership enforced on protected routes.
- Versioned SQLite migrations tracked in a `schema_migrations` table.
- Server-side form validation with user-facing error and success states.
- Weekly goal setting for training minutes and session count.
- Personal-record cards for longest session, peak effort, best week, streak, and total sessions.
- Workout session logging with date, time, duration, perceived intensity, recovery rating, sleep hours, source, and notes.
- Editable user profile for age and gender based cohort comparisons.
- Filterable workout ledger with dashboard metrics for volume, session count, duration, and intensity.
- 30-day fitness summary with weekly training volume, average session duration, and simple score projection.
- 8-week training trend analysis with weekly minutes, sessions, active days, best week, and consistency rate.
- Intensity-zone breakdown across recovery, base, hard, and peak training sessions.
- Recovery readiness analytics based on logged recovery scores, sleep hours, and high-effort risk flags.
- Recommendation cards that adapt to recent volume, intensity, consistency, and recovery signals.
- Population comparisons using public Kaggle datasets.
- Responsive dark fitness-dashboard UI built with Flask templates, CSS, and Chart.js.

## Tech stack

- Python
- Flask
- SQLite
- pandas
- Chart.js
- HTML/CSS/Jinja templates

## Project structure

```text
FitFuture/
├── fitfuture/
│   ├── __init__.py
│   ├── analytics.py
│   ├── analytics_routes.py
│   ├── auth.py
│   ├── config.py
│   ├── datasets.py
│   ├── db.py
│   ├── goals.py
│   ├── users.py
│   ├── validation.py
│   ├── utils.py
│   └── workouts.py
├── main.py
├── templates/
│   ├── auth.html
│   ├── base.html
│   ├── workouts.html
│   └── analytics.html
├── static/
│   └── styles.css
├── tests/
│   ├── conftest.py
│   ├── test_analytics.py
│   ├── test_auth_workouts.py
│   └── test_migrations.py
├── requirements.txt
├── gym_members_exercise_tracking.csv
├── health_fitness_tracking_365days.csv
├── health_fitness_dataset.csv
└── README.md
```

## Architecture

`main.py` is now a thin entrypoint that creates the Flask app. The application code lives in the `fitfuture/` package:

1. `__init__.py`
   Creates the Flask app, registers Blueprints, wires template/static folders, and initializes SQLite.
2. `auth.py`
   Handles login, registration, logout, session helpers, and route protection.
3. `workouts.py`
   Owns workout CRUD routes, filtering, dashboard metrics, and profile update behavior.
4. `analytics.py`
   Computes 30-day summaries, cohort percentiles, 8-week trends, intensity zones, recovery readiness, and recommendations.
5. `analytics_routes.py`
   Renders the analytics dashboard using the analytics service layer.
6. `datasets.py`
   Loads only the needed CSV columns and caches population summary stats.
7. `db.py`
   Runs versioned SQLite migrations, seeds the demo account, and exposes small query helpers.
8. `goals.py`
   Manages weekly goals, goal progress, and personal-record calculations.
9. `validation.py`
   Validates auth, profile, and workout forms before data reaches SQLite.
10. `config.py`, `users.py`, and `utils.py`
   Keep constants, profile lookup, parsing, and date utilities separated from route code.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Then open:

```text
http://127.0.0.1:5000
```

Demo login:

```text
Email: test@example.com
Password: fitfuture123
```

## Running tests

```bash
pytest
```

The test suite uses isolated temporary SQLite databases, so route and analytics tests do not mutate the local demo database.

## Portfolio highlights

- Demonstrates full-stack Flask development without hiding the backend behind a framework generator.
- Uses an app factory, Flask Blueprints, and separated service/data modules.
- Adds migration-backed SQLite persistence without introducing unnecessary framework weight.
- Includes session authentication and user-scoped CRUD behavior.
- Handles invalid form submissions with clear inline errors and success feedback.
- Adds user-configurable goals and personal-record calculations for product depth.
- Adds recovery and sleep tracking that feeds readiness-aware coaching.
- Shows practical data work with multiple large CSV datasets and cached pandas summaries.
- Uses custom analytics logic instead of static placeholder charts.
- Includes pytest coverage for auth, protected routes, validation, goals, workout ownership, migrations, and analytics helpers.
- Includes a cohesive product direction: training intelligence, cohort benchmarking, and next-step guidance.
- Keeps the first version simple enough to understand while leaving clear room for production-grade iteration.

## Roadmap

- Add SQLAlchemy or a richer repository layer if the schema grows.
- Add richer streak history and periodized training blocks.
- Deploy the app with production config and a public demo URL.

## Dataset citations

This project uses publicly available datasets from Kaggle:

1. Gym Members Exercise Tracking Dataset
   https://www.kaggle.com/datasets/valakhorasani/gym-members-exercise-dataset
2. Health & Fitness Tracking (365 Days) Dataset
   https://www.kaggle.com/datasets/waqasishtiaq/fitness
3. General Health & Wellness Dataset
   https://www.kaggle.com/datasets/evan65549/health-and-fitness-dataset

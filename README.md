# FitFuture

FitFuture is a Flask fitness intelligence dashboard that helps users log workouts, understand training consistency, and compare recent activity against public population datasets. The project is intentionally built as a portfolio-ready full-stack prototype: it combines CRUD workflows, SQLite persistence, data processing with pandas, Chart.js visualizations, and a polished responsive frontend.

## Product idea

Most simple workout trackers show what happened. FitFuture is designed to answer a more useful question:

> Am I training consistently enough, and how does my recent activity compare to similar people?

The app currently focuses on one demo user, but the architecture is ready to evolve toward authentication, multiple users, richer goals, and production deployment.

## Current features

- Login, logout, and registration with password hashing.
- Per-user workout ownership enforced on protected routes.
- Workout session logging with date, time, duration, perceived intensity, source, and notes.
- Editable user profile for age and gender based cohort comparisons.
- Filterable workout ledger with dashboard metrics for volume, session count, duration, and intensity.
- 30-day fitness summary with weekly training volume, average session duration, and simple score projection.
- 8-week training trend analysis with weekly minutes, sessions, active days, best week, and consistency rate.
- Intensity-zone breakdown across recovery, base, hard, and peak training sessions.
- Recommendation cards that adapt to recent volume, intensity, and consistency.
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
├── main.py
├── templates/
│   ├── base.html
│   ├── workouts.html
│   └── analytics.html
├── static/
│   └── styles.css
├── requirements.txt
├── gym_members_exercise_tracking.csv
├── health_fitness_tracking_365days.csv
├── health_fitness_dataset.csv
└── README.md
```

## Main file breakdown

`main.py` is organized into focused sections:

1. Database helpers
   Creates the SQLite tables, seeds a default user/profile, and provides reusable query helpers.
2. Dataset helpers
   Loads only the needed CSV columns and caches population summary stats.
3. Analytics helpers
   Computes recent training volume, cohort percentiles, 8-week trends, intensity zones, consistency, and recommendations.
4. Workout helpers
   Handles filters, workout form parsing, metrics, and CRUD data access.
5. Route handlers
   Renders the workouts and analytics views and processes profile/workout actions.

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
- Includes session authentication and user-scoped CRUD behavior.
- Shows practical data work with multiple large CSV datasets and cached pandas summaries.
- Uses custom analytics logic instead of static placeholder charts.
- Includes pytest coverage for auth, protected routes, workout ownership, and analytics helpers.
- Includes a cohesive product direction: training intelligence, cohort benchmarking, and next-step guidance.
- Keeps the first version simple enough to understand while leaving clear room for production-grade iteration.

## Roadmap

- Split the app into Flask Blueprints, service modules, and database modules.
- Add SQLAlchemy or migration-backed persistence.
- Add form validation and user-facing error states.
- Add goal setting, personal records, streak history, and recovery tracking.
- Deploy the app with production config and a public demo URL.

## Dataset citations

This project uses publicly available datasets from Kaggle:

1. Gym Members Exercise Tracking Dataset
   https://www.kaggle.com/datasets/valakhorasani/gym-members-exercise-dataset
2. Health & Fitness Tracking (365 Days) Dataset
   https://www.kaggle.com/datasets/waqasishtiaq/fitness
3. General Health & Wellness Dataset
   https://www.kaggle.com/datasets/evan65549/health-and-fitness-dataset

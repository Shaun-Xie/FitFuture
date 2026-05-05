# FitFuture

FitFuture is a Flask fitness tracking app where a user can log workouts, maintain a simple profile, and compare recent activity against public population datasets. The current version is intentionally lightweight, but it now has a cleaner structure that is easier to extend into a portfolio-ready project.

## What the app does

- Tracks workout sessions with date, duration, intensity, source, and notes.
- Stores a simple user profile for age and gender based comparisons.
- Summarizes recent training volume over the last 30 days.
- Estimates simple percentile comparisons using Kaggle datasets.
- Visualizes recent activity vs population averages with Chart.js.

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

`main.py` is now organized into four sections:

1. Database helpers
   Creates the SQLite tables, seeds a default user/profile, and provides small query helpers.
2. Dataset helpers
   Loads only the columns needed from the large CSVs and caches summary stats for analytics.
3. Analytics helpers
   Computes the 30 day workout summary, cohort comparisons, and chart data.
4. Route handlers
   Renders the workouts and analytics pages and handles create, update, delete, and profile actions.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Then open `http://127.0.0.1:5000`.

## Why this refactor matters

- App logic is separated from presentation.
- Templates and styling are now in standard Flask folders.
- The repo is easier to navigate and easier to deploy later.
- Large CSV files are read more efficiently by loading only the columns the app actually uses.

## Good next steps

- Split database logic into a dedicated module and add migrations.
- Add form validation and basic error handling.
- Introduce tests for analytics helpers and route behavior.
- Add environment based config and a production WSGI server for deployment.
- Replace the single hardcoded user flow with authentication.

## Dataset citations

This project uses publicly available datasets from Kaggle:

1. Gym Members Exercise Tracking Dataset
   https://www.kaggle.com/datasets/valakhorasani/gym-members-exercise-dataset
2. Health & Fitness Tracking (365 Days) Dataset
   https://www.kaggle.com/datasets/waqasishtiaq/fitness
3. General Health & Wellness Dataset
   https://www.kaggle.com/datasets/evan65549/health-and-fitness-dataset

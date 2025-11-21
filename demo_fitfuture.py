import pandas as pd

# --- 1. Load Kaggle health & fitness dataset ---
csv_path = "health_fitness_dataset.csv"  # make sure this file is in the same folder
df = pd.read_csv(csv_path)

print("=== FitFuture Tracker: Dataset Loaded ===")
print(f"Rows: {len(df)}, Columns: {len(df.columns)}")
print("Columns:", list(df.columns))
print()

# --- 2. Show some basic stats ---
print("=== Basic Summary (first 5 rows) ===")
print(df.head())
print()

print("=== Example Metrics Summary ===")
print(df[["age", "daily_steps", "hours_sleep", "fitness_level"]].describe())
print()

# --- 3. Simple percentile calculation for a sample user ---
def fitness_percentile(age, gender, fitness_value, age_window=3):
    """
    Estimate percentile of fitness_value for people with:
    - age in [age - age_window, age + age_window]
    - same gender

    Returns: percentile in [0, 100]
    """
    subset = df[
        (df["age"].between(age - age_window, age + age_window))
        & (df["gender"] == gender)
        & df["fitness_level"].notna()
    ]

    if subset.empty:
        return None, 0

    # Proportion of people with fitness_level <= this value
    pct = (subset["fitness_level"] <= fitness_value).mean() * 100.0
    return pct, len(subset)

# Example hypothetical user:
user_age = 25
user_gender = "M"
user_fitness = 65.0  # pretend this is their current fitness_level score

percentile, n = fitness_percentile(user_age, user_gender, user_fitness)

print("=== Sample User Comparison ===")
print(f"Hypothetical user -> age={user_age}, gender={user_gender}, "
      f"fitness_level={user_fitness}")

if percentile is None:
    print("Not enough comparison data for this age/gender group.")
else:
    print(f"Compared to {n} people in the dataset with similar age and gender:")
    print(f" -> This user is around the {percentile:.1f}th percentile "
          f"for fitness_level.")

from __future__ import annotations

from typing import Any

import pandas as pd

from . import config

EXTERNAL_STATS: dict[str, dict[str, Any]] = {}
DATAFRAMES: dict[str, pd.DataFrame] = {}


def add_mean_metrics(
    entry: dict[str, Any],
    df: pd.DataFrame,
    metrics: dict[str, str],
) -> None:
    for column_name, metric_name in metrics.items():
        if column_name in df.columns:
            entry[metric_name] = df[column_name].mean()


def compute_external_stats() -> dict[str, dict[str, Any]]:
    global EXTERNAL_STATS, DATAFRAMES

    if EXTERNAL_STATS:
        return EXTERNAL_STATS

    stats: dict[str, dict[str, Any]] = {}

    for dataset in config.DATASET_CONFIG:
        path = config.BASE_DIR / dataset["filename"]
        entry: dict[str, Any] = {"name": dataset["label"], "exists": False}

        if not path.exists():
            stats[dataset["key"]] = entry
            continue

        try:
            df = pd.read_csv(path, usecols=dataset["usecols"])
            header = pd.read_csv(path, nrows=0)

            DATAFRAMES[dataset["key"]] = df
            entry["exists"] = True
            entry["num_rows"] = len(df)
            entry["num_cols"] = len(header.columns)

            add_mean_metrics(entry, df, dataset["metrics"])
        except Exception as exc:
            entry["error"] = str(exc)

        stats[dataset["key"]] = entry

    EXTERNAL_STATS = stats
    return stats

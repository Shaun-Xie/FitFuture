from __future__ import annotations

from flask import Blueprint, render_template

from . import analytics as training_analytics
from . import datasets
from .auth import get_current_user_id, login_required
from .blocks import build_training_block_progress, get_training_block
from .goals import build_goal_progress, build_personal_records, get_user_goals

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@login_required
def dashboard() -> str:
    user_id = get_current_user_id()
    external_stats = datasets.compute_external_stats()
    fitness_summary = training_analytics.compute_fitness_summary(user_id)
    training_insights = training_analytics.build_training_insights(user_id)
    goals = get_user_goals(user_id)
    goal_progress = build_goal_progress(goals, training_insights)
    training_block = get_training_block(user_id)
    training_block_progress = build_training_block_progress(
        training_block,
        training_insights,
    )
    personal_records = build_personal_records(user_id, training_insights)
    recommendations = training_analytics.build_training_recommendations(
        fitness_summary,
        training_insights,
        training_block_progress,
    )

    chart_data = training_analytics.build_chart_data(
        external_stats,
        fitness_summary,
        training_insights,
    )
    chart_data["target_weekly_minutes"] = (
        training_block_progress.get("target_weekly_minutes")
        if training_block_progress.get("has_block")
        else goals["weekly_minutes_goal"]
    )

    return render_template(
        "analytics.html",
        active_view="analytics",
        external_stats=external_stats,
        fitness_summary=fitness_summary,
        training_insights=training_insights,
        goals=goals,
        goal_progress=goal_progress,
        training_block=training_block,
        training_block_progress=training_block_progress,
        personal_records=personal_records,
        recommendations=recommendations,
        chart_data=chart_data,
    )

from __future__ import annotations

from flask import Blueprint, render_template

from . import analytics as training_analytics
from . import datasets
from .auth import get_current_user_id, login_required

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@login_required
def dashboard() -> str:
    user_id = get_current_user_id()
    external_stats = datasets.compute_external_stats()
    fitness_summary = training_analytics.compute_fitness_summary(user_id)
    training_insights = training_analytics.build_training_insights(user_id)
    recommendations = training_analytics.build_training_recommendations(
        fitness_summary,
        training_insights,
    )

    return render_template(
        "analytics.html",
        active_view="analytics",
        external_stats=external_stats,
        fitness_summary=fitness_summary,
        training_insights=training_insights,
        recommendations=recommendations,
        chart_data=training_analytics.build_chart_data(
            external_stats,
            fitness_summary,
            training_insights,
        ),
    )

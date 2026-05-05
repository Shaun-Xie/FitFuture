from __future__ import annotations

from typing import Any

from flask import Flask

from . import config
from .analytics_routes import analytics_bp
from .auth import auth_bp, get_current_user
from .db import init_db
from .workouts import workouts_bp


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(config.BASE_DIR / "templates"),
        static_folder=str(config.BASE_DIR / "static"),
    )
    app.config.from_mapping(SECRET_KEY=config.SECRET_KEY)

    if test_config:
        app.config.update(test_config)

    app.register_blueprint(auth_bp)
    app.register_blueprint(workouts_bp)
    app.register_blueprint(analytics_bp)

    @app.context_processor
    def inject_current_user() -> dict[str, Any]:
        return {"current_user": get_current_user()}

    init_db()

    return app

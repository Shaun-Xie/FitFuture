from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import wraps
from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import config
from .db import ensure_default_profile, fetch_one, get_db
from .validation import validate_auth_form

auth_bp = Blueprint("auth", __name__)


def get_current_user() -> dict[str, Any] | None:
    user_id = session.get("user_id")
    if user_id is None:
        return None

    return fetch_one(
        "SELECT user_id, email, created_at, status FROM users WHERE user_id = ?",
        (user_id,),
    )


def get_current_user_id() -> int:
    user_id = session.get("user_id")
    if user_id is None:
        abort(401)

    return int(user_id)


def login_required(view: Any) -> Any:
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        if session.get("user_id") is None:
            return redirect(url_for("auth.login", next=request.path))

        return view(*args, **kwargs)

    return wrapped_view


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> Any:
    errors: list[str] = []

    if request.method == "POST":
        values, errors = validate_auth_form(
            request.form,
            require_password_length=False,
        )
        user = fetch_one("SELECT * FROM users WHERE email = ?", (values["email"],))

        if not errors and (
            user is None
            or not check_password_hash(user["password_hash"], values["password"])
        ):
            errors.append("Invalid email or password.")
        elif not errors and user["status"] != "ACTIVE":
            errors.append("This account is not active.")

        if not errors:
            session.clear()
            session["user_id"] = user["user_id"]
            flash("Welcome back. Your dashboard is ready.", "success")
            next_url = request.args.get("next") or url_for("workouts.index")
            return redirect(next_url if next_url.startswith("/") else url_for("workouts.index"))

    return (
        render_template(
            "auth.html",
            active_view="auth",
            mode="login",
            errors=errors,
            demo_email=config.DEMO_USER_EMAIL,
            demo_password=config.DEMO_USER_PASSWORD,
        ),
        400 if errors else 200,
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register() -> Any:
    errors: list[str] = []

    if request.method == "POST":
        values, errors = validate_auth_form(
            request.form,
            require_password_length=True,
        )

        if not errors:
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO users (email, password_hash, created_at, status)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            values["email"],
                            generate_password_hash(values["password"]),
                            datetime.utcnow().isoformat(),
                            "ACTIVE",
                        ),
                    )
                    user_id = int(cur.lastrowid)
                    ensure_default_profile(cur, user_id)
            except sqlite3.IntegrityError:
                errors.append("An account with that email already exists.")
            else:
                session.clear()
                session["user_id"] = user_id
                flash("Account created. Your private dashboard is ready.", "success")
                return redirect(url_for("workouts.index"))

    return (
        render_template(
            "auth.html",
            active_view="auth",
            mode="register",
            errors=errors,
            demo_email=config.DEMO_USER_EMAIL,
            demo_password=config.DEMO_USER_PASSWORD,
        ),
        400 if errors else 200,
    )


@auth_bp.route("/logout")
def logout() -> Any:
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))

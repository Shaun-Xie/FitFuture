from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import wraps
from typing import Any

from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import config
from .db import ensure_default_profile, fetch_one, get_db

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
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = fetch_one("SELECT * FROM users WHERE email = ?", (email,))

        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Invalid email or password."
        elif user["status"] != "ACTIVE":
            error = "This account is not active."
        else:
            session.clear()
            session["user_id"] = user["user_id"]
            next_url = request.args.get("next") or url_for("workouts.index")
            return redirect(next_url if next_url.startswith("/") else url_for("workouts.index"))

    return render_template(
        "auth.html",
        active_view="auth",
        mode="login",
        error=error,
        demo_email=config.DEMO_USER_EMAIL,
        demo_password=config.DEMO_USER_PASSWORD,
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register() -> Any:
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            error = "Email and password are required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        else:
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO users (email, password_hash, created_at, status)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            email,
                            generate_password_hash(password),
                            datetime.utcnow().isoformat(),
                            "ACTIVE",
                        ),
                    )
                    user_id = int(cur.lastrowid)
                    ensure_default_profile(cur, user_id)
            except sqlite3.IntegrityError:
                error = "An account with that email already exists."
            else:
                session.clear()
                session["user_id"] = user_id
                return redirect(url_for("workouts.index"))

    return render_template(
        "auth.html",
        active_view="auth",
        mode="register",
        error=error,
        demo_email=config.DEMO_USER_EMAIL,
        demo_password=config.DEMO_USER_PASSWORD,
    )


@auth_bp.route("/logout")
def logout() -> Any:
    session.clear()
    return redirect(url_for("auth.login"))

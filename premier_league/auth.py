"""Local accounts, role checks and CSRF protection."""

import os
import secrets
import sqlite3
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from premier_league.database import db_connection
from premier_league.paths import SESSION_KEY_PATH


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        def protected(*args, **kwargs):
            if not g.user:
                return redirect(url_for("auth.login"))
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)

        return protected

    return decorate


def configure_auth(app):
    # Persist the signing key locally; never commit it.
    key_path = SESSION_KEY_PATH
    key = app.config.get("SECRET_KEY") or os.environ.get("PREMIER_LEAGUE_SECRET_KEY")
    if not key:
        try:
            with open(key_path) as f:
                key = f.read().strip()
        except FileNotFoundError:
            key = secrets.token_hex(32)
            try:
                with open(
                    key_path, "x", opener=lambda path, flags: os.open(path, flags, 0o600)
                ) as f:
                    f.write(key)
            except FileExistsError:
                with open(key_path) as f:
                    key = f.read().strip()
    app.config.update(SECRET_KEY=key, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    @app.before_request
    def load_user():
        g.user = None
        if session.get("user_id"):
            with db_connection() as conn:
                try:
                    g.user = conn.execute(
                        "SELECT id, username, role, team_id FROM users WHERE id=?",
                        (session["user_id"],),
                    ).fetchone()
                except sqlite3.OperationalError:
                    session.clear()
        if request.method == "POST":
            token = session.get("csrf_token")
            if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
                abort(400, "Обновите страницу и повторите действие")

    @app.context_processor
    def auth_context():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return dict(current_user=g.user, csrf_token=session["csrf_token"])

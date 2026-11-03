"""Login and logout endpoints."""

import sqlite3
from flask import Blueprint, request, redirect, render_template, session, url_for
from werkzeug.security import check_password_hash
from premier_league.database import db_connection

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        with db_connection() as conn:
            try:
                user = conn.execute(
                    "SELECT * FROM users WHERE username=?", (request.form.get("username", ""),)
                ).fetchone()
            except sqlite3.OperationalError:
                user = None
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("admin.admin_panel"))
        error = "Неверное имя пользователя или пароль. Если аккаунтов ещё нет, создайте их по инструкции README."
    return render_template("login.html", error=error)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("public.index"))

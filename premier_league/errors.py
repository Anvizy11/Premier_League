"""Shared error pages."""

from flask import render_template


def request_error(error):
    return render_template("error.html", error=error), error.code


def register_errors(app):
    for code in (400, 403, 404, 409):
        app.register_error_handler(code, request_error)

"""Premier League application factory."""

from flask import Flask

from premier_league.auth import configure_auth
from premier_league.cli import register_cli
from premier_league.errors import register_errors
from premier_league.paths import PROJECT_ROOT


def create_app(config=None):
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.from_mapping(config or {})
    configure_auth(app)
    register_cli(app)
    register_errors(app)

    from premier_league.routes import admin, auth, discipline, events, lineups, matches, public

    for module in (auth, public, admin, matches, lineups, events, discipline):
        app.register_blueprint(module.bp)
    return app

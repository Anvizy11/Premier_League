"""Flask maintenance commands for schema and user accounts."""

import sqlite3
import click
from werkzeug.security import generate_password_hash
from premier_league.database import db_connection


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create missing tables without deleting existing records."""
        with db_connection(write=True) as conn:
            from premier_league.migrations import initialize_database

            initialize_database(conn)
        click.echo("Структура базы готова. Существующие данные сохранены.")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.option(
        "--role", type=click.Choice(["team_admin", "referee", "organizer"]), required=True
    )
    @click.option("--team-id", type=int)
    @click.password_option(confirmation_prompt=True)
    def create_user(username, role, team_id, password):
        if len(password) < 10:
            raise click.ClickException("Пароль должен содержать минимум 10 символов")
        if (role == "team_admin") != (team_id is not None):
            raise click.ClickException(
                "Для team_admin укажите --team-id; для других ролей он не нужен"
            )
        try:
            with db_connection(write=True) as conn:
                if (
                    team_id is not None
                    and not conn.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone()
                ):
                    raise click.ClickException("Команда не найдена")
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, team_id) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(password), role, team_id),
                )
        except sqlite3.IntegrityError:
            raise click.ClickException("Такое имя уже существует")
        click.echo(f"Создан пользователь {username}, роль: {role}")

    @app.cli.command("reset-password")
    @click.argument("username")
    def reset_password(username):
        """Set an existing account's password using hidden terminal input."""
        with db_connection() as conn:
            user = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if user is None:
            raise click.ClickException("Пользователь не найден")

        password = click.prompt(
            "Новый пароль", hide_input=True, confirmation_prompt="Повторите пароль"
        )
        if len(password) < 10:
            raise click.ClickException("Пароль должен содержать минимум 10 символов")

        password_hash = generate_password_hash(password)
        with db_connection(write=True) as conn:
            result = conn.execute(
                "UPDATE users SET password_hash=? WHERE id=? AND username=?",
                (password_hash, user["id"], username),
            )
            if result.rowcount != 1:
                raise click.ClickException("Пользователь не найден")
        click.echo(f"Пароль пользователя {username} обновлён.")

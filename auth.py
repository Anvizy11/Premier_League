"""Local accounts, role checks and CSRF protection."""
import os
import secrets
import sqlite3
from functools import wraps

import click
from flask import abort, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from database import db_connection


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        def protected(*args, **kwargs):
            if not g.user:
                return redirect(url_for('login'))
            if g.user['role'] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return protected
    return decorate


def configure_auth(app):
    # Persist the signing key locally; never commit it.
    key_path = os.path.join(app.root_path, '.session_key')
    key = os.environ.get('PREMIER_LEAGUE_SECRET_KEY')
    if not key:
        try:
            with open(key_path) as f:
                key = f.read().strip()
        except FileNotFoundError:
            key = secrets.token_hex(32)
            try:
                with open(key_path, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as f:
                    f.write(key)
            except FileExistsError:
                with open(key_path) as f:
                    key = f.read().strip()
    app.config.update(SECRET_KEY=key, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

    @app.before_request
    def load_user():
        g.user = None
        if session.get('user_id'):
            with db_connection() as conn:
                try:
                    g.user = conn.execute('SELECT id, username, role, team_id FROM users WHERE id=?', (session['user_id'],)).fetchone()
                except sqlite3.OperationalError:
                    session.clear()
        if request.method == 'POST':
            token = session.get('csrf_token')
            if not token or not secrets.compare_digest(token, request.form.get('csrf_token', '')):
                abort(400, 'Обновите страницу и повторите действие')

    @app.context_processor
    def auth_context():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        return dict(current_user=g.user, csrf_token=session['csrf_token'])

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            with db_connection() as conn:
                try:
                    user = conn.execute('SELECT * FROM users WHERE username=?', (request.form.get('username', ''),)).fetchone()
                except sqlite3.OperationalError:
                    user = None
            if user and check_password_hash(user['password_hash'], request.form.get('password', '')):
                session.clear()
                session['user_id'] = user['id']
                return redirect(url_for('admin_panel'))
            error = 'Неверное имя пользователя или пароль. Если аккаунтов ещё нет, создайте их по инструкции README.'
        return render_template('login.html', error=error)

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('index'))

    @app.cli.command('init-db')
    def init_db():
        """Create missing tables without deleting existing records."""
        with db_connection(write=True) as conn:
            from migrations import initialize_database
            initialize_database(conn)
        click.echo('Структура базы готова. Существующие данные сохранены.')

    @app.cli.command('create-user')
    @click.argument('username')
    @click.option('--role', type=click.Choice(['team_admin', 'referee', 'organizer']), required=True)
    @click.option('--team-id', type=int)
    @click.password_option(confirmation_prompt=True)
    def create_user(username, role, team_id, password):
        if len(password) < 10:
            raise click.ClickException('Пароль должен содержать минимум 10 символов')
        if (role == 'team_admin') != (team_id is not None):
            raise click.ClickException('Для team_admin укажите --team-id; для других ролей он не нужен')
        try:
            with db_connection(write=True) as conn:
                if team_id is not None and not conn.execute('SELECT 1 FROM teams WHERE id=?', (team_id,)).fetchone():
                    raise click.ClickException('Команда не найдена')
                conn.execute('INSERT INTO users (username, password_hash, role, team_id) VALUES (?, ?, ?, ?)',
                             (username, generate_password_hash(password), role, team_id))
        except sqlite3.IntegrityError:
            raise click.ClickException('Такое имя уже существует')
        click.echo(f'Создан пользователь {username}, роль: {role}')

import hmac
import secrets
from functools import wraps

import click
from flask import (
    abort,
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from dnd_manager.infrastructure.database import get_db

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15
DELETE_OLD_ATTEMPTS = "DELETE FROM login_attempt WHERE attempted_at < datetime('now', ?)"
COUNT_ATTEMPTS = "SELECT COUNT(*) FROM login_attempt WHERE ip_address = ?"
bp = Blueprint("auth", __name__, url_prefix="/mj")


def is_gm():
    return session.get("is_gm") is True


def gm_required(view):
    return wraps(view)(lambda **kwargs: gm_view(view, kwargs))


def gm_view(view, arguments):
    if not is_gm():
        return redirect(url_for("auth.login", next=request.path))
    return view(**arguments)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validate_csrf():
    expected = session.get("csrf_token", "")
    received = request.form.get("csrf_token", "")
    if not valid_csrf(expected, received):
        abort(400, "Jeton CSRF invalide.")


def valid_csrf(expected, received):
    return bool(expected) and hmac.compare_digest(expected, received)


@bp.route("/connexion", methods=("GET", "POST"))
def login():
    return LOGIN_HANDLERS[request.method]()


def show_login():
    return render_template("auth/login.html")


def submit_login():
    validate_csrf()
    database, ip_address = get_db(), request.remote_addr or "inconnue"
    discard_expired_attempts(database)
    enforce_attempt_limit(database, ip_address)
    return authenticate(database, ip_address)


def discard_expired_attempts(database):
    window = f"-{LOGIN_WINDOW_MINUTES} minutes"
    database.execute(DELETE_OLD_ATTEMPTS, (window,))


def enforce_attempt_limit(database, ip_address):
    count = database.execute(COUNT_ATTEMPTS, (ip_address,)).fetchone()[0]
    if count >= MAX_LOGIN_ATTEMPTS:
        database.commit()
        abort(429, f"Trop de tentatives. Réessaie dans {LOGIN_WINDOW_MINUTES} minutes.")


def authenticate(database, ip_address):
    password_hash = current_app.config.get("GM_PASSWORD_HASH")
    password = request.form.get("password", "")
    handler = successful_login if valid_password(password_hash, password) else failed_login
    return handler(database, ip_address)


def valid_password(password_hash, password):
    return bool(password_hash) and check_password_hash(password_hash, password)


def successful_login(database, ip_address):
    database.execute("DELETE FROM login_attempt WHERE ip_address = ?", (ip_address,))
    database.commit()
    open_gm_session()
    return redirect(url_for("main.campaign"))


def open_gm_session():
    session.clear()
    session["is_gm"] = True
    session["csrf_token"] = secrets.token_urlsafe(32)


def failed_login(database, ip_address):
    database.execute("INSERT INTO login_attempt (ip_address) VALUES (?)", (ip_address,))
    database.commit()
    flash("Mot de passe incorrect.", "error")
    return show_login()


@bp.post("/deconnexion")
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for("main.campaign"))


LOGIN_HANDLERS = {"GET": show_login, "POST": submit_login}


def init_app(app):
    app.register_blueprint(bp)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["is_gm"] = is_gm
    app.cli.add_command(hash_password_command)


@click.command("hash-password")
@click.password_option(confirmation_prompt=True)
def hash_password_command(password):
    """Génère le hash à placer dans GM_PASSWORD_HASH."""
    click.echo(generate_password_hash(password))

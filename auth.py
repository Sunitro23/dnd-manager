import hmac
import secrets
from functools import wraps

import click
from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15


def is_gm():
    return session.get("is_gm") is True


def gm_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if not is_gm():
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)

    return wrapped_view


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validate_csrf():
    expected = session.get("csrf_token", "")
    received = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, received):
        abort(400, "Jeton CSRF invalide.")


def init_app(app):
    from flask import Blueprint

    bp = Blueprint("auth", __name__, url_prefix="/mj")

    @bp.route("/connexion", methods=("GET", "POST"))
    def login():
        if request.method == "POST":
            validate_csrf()
            database = get_db()
            ip_address = request.remote_addr or "inconnue"
            database.execute(
                """
                DELETE FROM login_attempt
                WHERE attempted_at < datetime('now', ?)
                """,
                (f"-{LOGIN_WINDOW_MINUTES} minutes",),
            )
            attempt_count = database.execute(
                """
                SELECT COUNT(*)
                FROM login_attempt
                WHERE ip_address = ?
                """,
                (ip_address,),
            ).fetchone()[0]
            if attempt_count >= MAX_LOGIN_ATTEMPTS:
                database.commit()
                abort(
                    429,
                    f"Trop de tentatives. Réessaie dans {LOGIN_WINDOW_MINUTES} minutes.",
                )

            password_hash = current_app.config.get("GM_PASSWORD_HASH")
            password = request.form.get("password", "")

            if password_hash and check_password_hash(password_hash, password):
                database.execute(
                    "DELETE FROM login_attempt WHERE ip_address = ?",
                    (ip_address,),
                )
                database.commit()
                session.clear()
                session["is_gm"] = True
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("main.campaign"))

            database.execute(
                "INSERT INTO login_attempt (ip_address) VALUES (?)",
                (ip_address,),
            )
            database.commit()
            flash("Mot de passe incorrect.", "error")

        return render_template("auth/login.html")

    @bp.post("/deconnexion")
    def logout():
        validate_csrf()
        session.clear()
        return redirect(url_for("main.campaign"))

    app.register_blueprint(bp)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["is_gm"] = is_gm
    app.cli.add_command(hash_password_command)


@click.command("hash-password")
@click.password_option(confirmation_prompt=True)
def hash_password_command(password):
    """Génère le hash à placer dans GM_PASSWORD_HASH."""
    click.echo(generate_password_hash(password))

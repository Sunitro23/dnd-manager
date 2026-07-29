import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix


def environment_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        GM_PASSWORD_HASH=os.environ.get("GM_PASSWORD_HASH"),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=environment_flag("SESSION_COOKIE_SECURE"),
        DATABASE_PATH=os.environ.get(
            "DATABASE_PATH",
            str(Path(app.instance_path) / "dnd_manager.sqlite3"),
        ),
        PORTRAIT_PATH=os.environ.get(
            "PORTRAIT_PATH",
            str(Path(app.instance_path) / "portraits"),
        ),
    )

    if test_config:
        app.config.update(test_config)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["PORTRAIT_PATH"]).mkdir(parents=True, exist_ok=True)

    import admin
    import auth
    import characters
    import database
    import routes

    database.init_app(app)
    auth.init_app(app)
    app.register_blueprint(routes.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(characters.bp)

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self'; "
            "script-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def expected_error(error):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=False, message=error.description), error.code
        return (
            render_template(
                "error.html",
                status=error.code,
                title=error.name,
                message=error.description,
            ),
            error.code,
        )

    return app

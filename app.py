import os
import sqlite3
from pathlib import Path

from flask import Flask, current_app, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from dnd_manager.infrastructure import database
from dnd_manager.authentication import http as auth_http
from dnd_manager.campaign import http as campaign_http
from dnd_manager.characters import http as characters_http
from dnd_manager.characters.administration import http as administration_http
from dnd_manager.character_api import http as character_api_http
from dnd_manager.ruleset import http as ruleset_http

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; object-src 'none'; base-uri 'self'; "
    "frame-ancestors 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
BASE_CONFIG = {
    "SECRET_KEY": os.environ.get("SECRET_KEY"),
    "GM_PASSWORD_HASH": os.environ.get("GM_PASSWORD_HASH"),
    "API_TOKEN": os.environ.get("API_TOKEN"),
    "API_CORS_ORIGIN": os.environ.get("API_CORS_ORIGIN", "*"),
    "MAX_CONTENT_LENGTH": 2 * 1024 * 1024,
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
}


def environment_flag(name, default=False):
    value = os.environ.get(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    configure_app(app, test_config)
    prepare_storage(app)
    register_components(app)
    return app


def configure_app(app, test_config):
    app.config.from_mapping(BASE_CONFIG)
    app.config.from_mapping(runtime_paths(app))
    apply_test_config(app, test_config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def runtime_paths(app):
    database = os.environ.get("DATABASE_PATH", str(Path(app.instance_path) / "dnd_manager.sqlite3"))
    portraits = os.environ.get("PORTRAIT_PATH", str(Path(app.instance_path) / "portraits"))
    engine_data = str(Path(app.root_path) / "engine_data.json")
    return {"DATABASE_PATH": database, "PORTRAIT_PATH": portraits,
            "ENGINE_DATA_PATH": engine_data,
            "OPENAPI_PATH": str(Path(app.root_path) / "openapi.yaml"),
            "API_PUBLIC": environment_flag("API_PUBLIC", True),
            "SESSION_COOKIE_SECURE": environment_flag("SESSION_COOKIE_SECURE")}


def apply_test_config(app, test_config):
    if test_config:
        app.config.update(test_config)


def prepare_storage(app):
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["PORTRAIT_PATH"]).mkdir(parents=True, exist_ok=True)


def register_components(app):
    database.init_app(app)
    auth_http.init_app(app)
    register_blueprints(app, application_blueprints())
    register_hooks(app)


def application_blueprints():
    return (campaign_http.bp, administration_http.bp, characters_http.bp,
            character_api_http.bp, ruleset_http.bp)


def register_blueprints(app, blueprints):
    for blueprint in blueprints:
        app.register_blueprint(blueprint)


def register_hooks(app):
    app.after_request(secure_response)
    app.register_error_handler(sqlite3.Error, storage_error)
    for status in (400, 404, 409, 413, 429, 503):
        app.register_error_handler(status, expected_error)


def secure_response(response):
    response.headers.update(SECURITY_HEADERS)
    add_api_access_headers(response)
    add_transport_security(response, request.is_secure)
    return response


def add_api_access_headers(response):
    if not request.path.startswith("/api/v1"):
        return
    add_allowed_origin(response, current_api_origin())
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, If-None-Match"
    response.headers["Access-Control-Allow-Methods"] = "GET, PUT, OPTIONS"
    response.headers["Access-Control-Expose-Headers"] = "ETag"


def add_allowed_origin(response, origin):
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin


def current_api_origin():
    configured = current_app.config["API_CORS_ORIGIN"]
    if configured == "*":
        return "*"
    return configured if request.headers.get("Origin") == configured else None


def add_transport_security(response, secure):
    if secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def expected_error(error):
    handlers = {True: asynchronous_error, False: html_error}
    return handlers[asynchronous_request()](error)


def asynchronous_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def asynchronous_error(error):
    return jsonify(ok=False, message=error.description), error.code


def html_error(error):
    context = {"status": error.code, "title": error.name, "message": error.description}
    return render_template("error.html", **context), error.code


def storage_error(_error):
    message = "Le stockage est momentanément indisponible."
    if asynchronous_request():
        return jsonify(ok=False, message=message), 503
    return render_template("error.html", status=503, title="Service indisponible",
                           message=message), 503

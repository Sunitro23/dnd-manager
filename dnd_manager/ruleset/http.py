from flask import Blueprint, current_app, jsonify, request, send_file

from dnd_manager.api_access import authentication_required, token_is_valid
from dnd_manager.infrastructure.database import get_db
from dnd_manager.ruleset.sqlite_catalog import SqliteRulesetCatalog
from dnd_manager.shared.errors import RepositoryUnavailable

bp = Blueprint("ruleset_api", __name__, url_prefix="/api/v1")


@bp.before_request
def authenticate():
    if authentication_required() and not token_is_valid():
        return jsonify({"error": {"status": 401, "message": "Authentification API requise."}}), 401


@bp.get("/")
def api_capabilities():
    return jsonify({"version": "v1", "public": current_app.config["API_PUBLIC"],
                    "openapi": "/api/v1/openapi.yaml",
                    "ruleset": "/api/v1/rulesets/current",
                    "characters": "/api/v1/characters",
                    "combat_profile": "/api/v1/characters/{character_id}/combat-profile"})


@bp.get("/openapi.yaml")
def openapi_contract():
    return send_file(current_app.config["OPENAPI_PATH"], mimetype="application/yaml")


@bp.get("/rulesets/current")
def current_ruleset():
    try:
        return ruleset_response(catalog().current())
    except RepositoryUnavailable as error:
        return jsonify({"error": {"status": 503, "message": str(error)}}), 503


def ruleset_response(bundle):
    revision = bundle["revision"]
    if request.if_none_match.contains(revision):
        return "", 304
    response = jsonify(bundle)
    response.set_etag(revision)
    response.cache_control.private = True
    response.cache_control.max_age = 3600
    return response


def catalog():
    return SqliteRulesetCatalog(get_db())

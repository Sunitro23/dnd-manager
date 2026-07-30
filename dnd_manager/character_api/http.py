from dataclasses import asdict

from flask import Blueprint, current_app, jsonify, request

from dnd_manager.api_access import authentication_required, token_is_valid
from dnd_manager.character_api.application import (
    ListCharacters,
    ReadCharacter,
    SyncCharacterHealth,
    SyncCharacterResource,
)
from dnd_manager.character_api.contracts import HealthSyncCommand, ResourceSyncCommand
from dnd_manager.character_api.combat_profile import build_combat_profile
from dnd_manager.character_api.sqlite_repository import SqliteCharacterExchangeRepository
from dnd_manager.infrastructure.database import get_db
from dnd_manager.ruleset.catalog import JsonRulesetCatalog
from dnd_manager.shared.errors import (
    ConcurrentUpdate,
    InvalidRequest,
    RepositoryUnavailable,
    ResourceNotFound,
)

bp = Blueprint("character_api", __name__, url_prefix="/api/v1")
ERROR_STATUS = {InvalidRequest: 400, ResourceNotFound: 404,
                ConcurrentUpdate: 409, RepositoryUnavailable: 503}


@bp.before_request
def authenticate():
    if authentication_required() and not token_is_valid():
        return api_error("Authentification API requise.", 401)


@bp.get("/characters/<int:character_id>")
def read_character(character_id):
    return execute(lambda: character_response(reader().execute(character_id)))


@bp.get("/characters/<int:character_id>/combat-profile")
def read_combat_profile(character_id):
    return execute(lambda: combat_profile_response(reader().execute(character_id)))


def combat_profile_response(snapshot):
    bundle = ruleset_catalog().current()
    profile = build_combat_profile(snapshot, bundle)
    return versioned_response(profile, profile_etag(snapshot, bundle))


def profile_etag(snapshot, bundle):
    return f"{snapshot.version}-{bundle['revision'][7:23]}"


def character_response(snapshot):
    revision = ruleset_revision()
    return versioned_response(asdict(snapshot) | {"ruleset_revision": revision},
                              str(snapshot.version))


def versioned_response(payload, etag):
    if request.if_none_match.contains(etag):
        return "", 304
    response = jsonify(payload)
    response.set_etag(etag)
    return response


@bp.get("/characters")
def list_characters():
    return execute(lambda: jsonify({"characters": serialized(lister().execute())}))


@bp.put("/characters/<int:character_id>/health")
def sync_health(character_id):
    return execute(lambda: jsonify(asdict(syncer().execute(character_id, health_command()))))


@bp.put("/characters/<int:character_id>/resources/<path:resource_key>")
def sync_resource(character_id, resource_key):
    return execute(lambda: resource_response(character_id, resource_key))


def resource_response(character_id, resource_key):
    result = resource_syncer().execute(character_id, resource_key, resource_command())
    return jsonify(asdict(result))


def serialized(values):
    return [asdict(value) for value in values]


def health_command():
    payload = request.get_json(silent=True) or {}
    try:
        return HealthSyncCommand(int(payload["current_hp"]), int(payload["expected_version"]))
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidRequest("Corps JSON invalide.") from error


def resource_command():
    payload = request.get_json(silent=True) or {}
    try:
        return ResourceSyncCommand(int(payload["spent"]), int(payload["expected_version"]))
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidRequest("Corps JSON invalide.") from error


def execute(operation):
    try:
        return operation()
    except tuple(ERROR_STATUS) as error:
        return api_error(str(error), ERROR_STATUS[type(error)])


def api_error(message, status):
    return jsonify({"error": {"status": status, "message": message}}), status


def reader():
    return ReadCharacter(SqliteCharacterExchangeRepository(get_db()))


def lister():
    return ListCharacters(SqliteCharacterExchangeRepository(get_db()))


def syncer():
    return SyncCharacterHealth(SqliteCharacterExchangeRepository(get_db()))


def resource_syncer():
    return SyncCharacterResource(SqliteCharacterExchangeRepository(get_db()))


def ruleset_revision():
    return ruleset_catalog().current()["revision"]


def ruleset_catalog():
    return JsonRulesetCatalog(current_app.config["ENGINE_DATA_PATH"])

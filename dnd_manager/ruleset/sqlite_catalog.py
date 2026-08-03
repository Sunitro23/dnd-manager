import hashlib
import json

from dnd_manager.paths.repository import list_paths


class SqliteRulesetCatalog:
    """Construit le contrat public directement depuis le catalogue canonique."""

    def __init__(self, database):
        self.database = database

    def current(self):
        paths = list_paths(self.database)
        bundle = {
            "schema_version": "1.0.0",
            "ruleset": {"id": "dark-souls-d6", "name": "Dark Souls D6",
                        "version": "3.0.0", "locale": "fr"},
            "definitions": definitions(),
            "character_options": character_options(self.database, paths),
            "coverage": coverage(paths),
            "features": features(paths),
        }
        bundle["revision"] = revision(bundle)
        return bundle


def definitions():
    abilities = {
        "strength": "Force", "dexterity": "Dextérité", "constitution": "Constitution",
        "intelligence": "Intelligence", "wisdom": "Sagesse", "charisma": "Charisme",
    }
    defenses = {"physical": "constitution", "elemental": "intelligence",
                "spiritual": "wisdom"}
    return {
        "abilities": {key: {"label": label} for key, label in abilities.items()},
        "defenses": {key: {"ability": ability} for key, ability in defenses.items()},
        "damage_types": {key: {"id": key} for key in (
            "physical", "elemental", "spiritual", "poison", "fire", "ice",
            "lightning", "light", "dark", "magic", "untyped",
        )},
        "rest_types": {"short_rest": {"id": "short_rest"},
                       "long_rest": {"id": "long_rest"}},
        "units": {"distance": "meter"},
    }


def character_options(database, paths):
    classes = database.execute(
        "SELECT id,stable_key,name,hit_die FROM character_class "
        "WHERE configured=1 ORDER BY name COLLATE NOCASE"
    ).fetchall()
    species = database.execute(
        "SELECT id,stable_key,name,physical_bonus,elemental_bonus,spiritual_bonus "
        "FROM species WHERE configured=1 ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return {
        "classes": [{"id": row["stable_key"], "name": row["name"],
                     "hit_die": row["hit_die"], "paths": origin_paths(paths, "class", row["id"])}
                    for row in classes],
        "species": [{"id": row["stable_key"], "name": row["name"],
                     "base_defenses": {key: row[f"{key}_bonus"] for key in (
                         "physical", "elemental", "spiritual")},
                     "paths": origin_paths(paths, "racial", row["id"])}
                    for row in species],
    }


def origin_paths(paths, path_type, origin_id):
    return [{"id": path["stable_key"], "name": path["name"]}
            for path in paths if path["path_type"] == path_type
            and path[f"{'class' if path_type == 'class' else 'species'}_id"] == origin_id]


def features(paths):
    return [feature(path, rank, capability) for path in paths for rank in path["ranks"]
            for capability in rank["capability_details"]]


def feature(path, rank, capability):
    mode = "passive" if capability["execution_mode"] == "permanent" else "active"
    contract = capability["contract"]
    activation = {"type": capability["execution_mode"],
                  "cost": capability["action_cost"],
                  "trigger": capability["trigger_event"],
                  "limit": capability["activation_limit"]}
    return {
        "id": contract["id"], "rank_id": rank["id"], "name": capability["name"],
        "mode": mode, "owner": {"path_id": path["stable_key"]},
        "activation": activation, "resource": capability_resource(capability),
        "description": capability["description"],
        "resolution": {"support": capability["execution_support"],
                       "targeting": contract["targeting"],
                       "operations": contract["operations"]},
    }


def capability_resource(capability):
    if not capability["uses_maximum"]:
        return None
    return {"id": f"{capability['stable_key']}.uses",
            "maximum": capability["uses_maximum"], "cost": 1,
            "recovery": [capability["recharge"]]}


def activation_key(label):
    return {"Action": "action", "Action bonus": "bonus_action", "Réaction": "reaction",
            "Libre": "free"}.get(label, label or "special")


def coverage(paths):
    capabilities = [capability for path in paths for rank in path["ranks"]
                    for capability in rank["capability_details"]]
    return {"total": len(capabilities),
            "full": sum(item["execution_support"] == "full" for item in capabilities),
            "partial": sum(item["execution_support"] == "partial" for item in capabilities),
            "none": sum(item["execution_support"] == "none" for item in capabilities)}


def revision(bundle):
    payload = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"

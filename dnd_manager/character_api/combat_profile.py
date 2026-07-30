from dataclasses import asdict


def build_combat_profile(snapshot, bundle):
    return {
        "schema_version": "1.0.0",
        "ruleset_revision": bundle["revision"],
        "character": character_values(snapshot),
        "features": unlocked_features(snapshot.feature_ids, bundle["features"]),
    }


def character_values(snapshot):
    return {
        "id": snapshot.character_id, "version": snapshot.version, "name": snapshot.name,
        "health": {"current": snapshot.current_hp, "maximum": snapshot.maximum_hp},
        "movement": {"size": snapshot.size, "speed": snapshot.speed},
        "abilities": serialized(snapshot.abilities),
        "defenses": serialized(snapshot.base_defenses),
        "equipment": serialized(snapshot.equipment),
        "resources": serialized(snapshot.resources),
    }


def unlocked_features(feature_ids, features):
    unlocked = set(feature_ids)
    return [combat_feature(feature) for feature in features if feature["id"] in unlocked]


def combat_feature(feature):
    keys = ("id", "name", "mode", "activation", "resource", "description")
    projected = {key: feature[key] for key in keys}
    return projected | {"resolution": combat_resolution(feature["resolution"])}


def combat_resolution(resolution):
    keys = ("support", "operations", "facts")
    return {key: resolution[key] for key in keys if key in resolution}


def serialized(values):
    return [asdict(value) for value in values]

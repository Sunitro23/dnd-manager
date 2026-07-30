import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from dnd_manager.ruleset.descriptions import describe  # noqa: E402
from dnd_manager.ruleset.extraction import extract_facts, operation_skeletons  # noqa: E402
from dnd_manager.ruleset.validation import validate_engine_rules  # noqa: E402

SOURCE = ROOT / "game_data.json"
RULES = ROOT / "engine_rules.json"
TARGET = ROOT / "engine_data.json"
ABILITY_LABELS = {
    "strength": "Force", "dexterity": "Dextérité", "constitution": "Constitution",
    "intelligence": "Intelligence", "wisdom": "Sagesse", "charisma": "Charisme",
}
DEFENSE_ABILITIES = {"physical": "constitution", "elemental": "intelligence",
                     "spiritual": "wisdom"}
ABILITY_ABBREVIATIONS = {
    "FOR": "strength", "DEX": "dexterity", "CON": "constitution",
    "INT": "intelligence", "SAG": "wisdom", "CHA": "charisma",
}


def build(source, engine_rules=None):
    rules = engine_rules or load_engine_rules()
    features = list(all_features(source, rules))
    require_known_rules(features, rules)
    bundle = {"schema_version": "1.0.0", "ruleset": ruleset(source),
              "definitions": definitions(source), "character_options": character_options(source),
              "coverage": coverage(features, source),
              "features": features}
    bundle["revision"] = revision(bundle)
    return bundle


def ruleset(source):
    value = source["ruleset"]
    return {"id": value["id"], "name": value["name"], "version": "2.0.0",
            "locale": value["locale"]}


def definitions(source):
    return {"abilities": abilities(), "defenses": defenses(),
            "damage_types": keyed(source, "damage_types"),
            "rest_types": keyed(source, "rest_types"),
            "rest_aliases": {"bonfire_rest": "long_rest"},
            "resources": resources(),
            "identifier_aliases": identifier_aliases(),
            "units": {"distance": "meter"}}


def abilities():
    return {key: {"label": label, "modifier": {"type": "floor",
                                               "formula": "(score - 10) / 2"}}
            for key, label in ABILITY_LABELS.items()}


def defenses():
    return {key: {"ability": ability} for key, ability in DEFENSE_ABILITIES.items()}


def resources():
    return {
        "humanity": {"label": "Humanité", "value_type": "counter"},
        "carcassage": {"label": "Carcassage", "value_type": "counter"},
        "emotion": {"label": "Émotion", "value_type": "collection"},
        "curse": {"label": "Malédiction", "value_type": "collection"},
        "guilt": {"label": "Faute révélée", "value_type": "collection"},
    }


def identifier_aliases():
    path_aliases = {
        "path.creations-de-nito.revenant-ossuaire":
            "path.enfant-des-tenebres.enfant-de-la-mort",
        "path.creations-de-nito.porte-peste":
            "path.enfant-des-tenebres.enfant-de-la-mort",
        "path.enfants-de-manus.bete-abyssale":
            "path.enfant-des-tenebres.enfant-des-abysses",
        "path.enfants-de-manus.rejeton-royal":
            "path.enfant-des-tenebres.enfant-des-abysses",
    }
    aliases = {"species.creations-de-nito": "species.enfant-des-tenebres",
               "species.enfants-de-manus": "species.enfant-des-tenebres", **path_aliases}
    for old, new in path_aliases.items():
        aliases.update(rank_aliases(old, new))
    return aliases


def rank_aliases(old_path, new_path):
    aliases = {}
    for rank in range(1, 6):
        old, new = f"{old_path}.rank-{rank}", f"{new_path}.rank-{rank}"
        aliases |= {old: new, f"{old}.active": f"{new}.active",
                    f"{old}.passive": f"{new}.passive", f"{old}.uses": f"{new}.uses"}
    return aliases


def keyed(source, name):
    return {item["id"]: item for item in source["definitions"][name]}


def character_options(source):
    return {"classes": [class_option(item) for item in source["classes"]],
            "species": [species_option(item) for item in source["races"]]}


def class_option(item):
    return {"id": item["id"], "name": item["name"], "hit_die": item["hit_die"],
            "primary_ability": ABILITY_ABBREVIATIONS[item["ability_bonus"]],
            "paths": [{"id": path["id"], "name": path["name"]} for path in item["paths"]]}


def species_option(item):
    return {"id": item["id"], "name": item["name"],
            "base_defenses": item["defenses"],
            "paths": [racial_path_option(path) for path in item["paths"]]}


def racial_path_option(path):
    return {"id": path["id"], "name": path["name"],
            "ability_bonuses": parse_ability_bonuses(path["abilities"]),
            "defense_bonuses": path.get("defenses", zero_defenses())}


def parse_ability_bonuses(value):
    parts = (part.strip().split() for part in value.split(","))
    return {ABILITY_ABBREVIATIONS[abbreviation]: int(amount)
            for amount, abbreviation in parts}


def zero_defenses():
    return {"physical": 0, "elemental": 0, "spiritual": 0}


def all_features(source, engine_rules):
    for group in ("classes", "races"):
        for option in source[group]:
            for path in option["paths"]:
                yield from path_features(option, path, engine_rules)


def path_features(option, path, engine_rules):
    for rank in path["ranks"]:
        for mode in ("active", "passive"):
            value = rank.get(mode)
            if value:
                yield feature(option, path, rank, mode, value, engine_rules)


def feature(option, path, rank, mode, value, engine_rules):
    feature_id = f"{rank['id']}.{mode}"
    resolved = resolution(feature_id, value, engine_rules)
    return {"id": feature_id, "rank_id": rank["id"], "name": rank["name"],
            "mode": mode, "owner": {"id": option["id"], "path_id": path["id"]},
            "activation": activation(mode, value), "resource": value.get("resource"),
            "description": description(resolved, value), "resolution": resolved}


def activation(mode, value):
    if mode == "passive":
        return {"type": "passive", "frequency": value.get("frequency")}
    return value["activation"]


def resolution(feature_id, value, engine_rules):
    if feature_id in engine_rules:
        return engine_rules[feature_id]
    facts = extract_facts(value["effect"])
    return {"support": "partial", "operations": operation_skeletons(facts), "facts": facts,
            "unstructured_rule": value["effect"],
            "missing": missing_requirements(facts)}


def description(resolved, value):
    return describe(resolved) if resolved["support"] == "full" else value["effect"]


def load_engine_rules():
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    return validate_engine_rules(rules)


def coverage(features, source):
    supports = ("full", "partial", "reference")
    counts = {support: sum(feature["resolution"]["support"] == support
                           for feature in features) for support in supports}
    return {"total": len(features), **counts,
            "facts": occurrence_counts(features, "facts"),
            "missing": occurrence_counts(features, "missing"),
            "catalog_gaps": catalogue_gaps(source)}


def missing_requirements(facts):
    missing = ["operation_parameters"]
    mechanics = facts.get("mechanics", ())
    if any(value in mechanics for value in ("damage", "heal", "movement", "status")):
        missing.append("targeting")
    if facts.get("saving_throws"):
        missing.append("saving_throw_difficulty")
    if "choice" in mechanics:
        missing.append("choice_branches")
    if "condition" in mechanics:
        missing.append("conditions")
    if facts.get("resource_refs"):
        missing.append("resource_state")
    if "damage" in mechanics and not facts.get("damage_types"):
        missing.append("damage_type")
    return missing


def occurrence_counts(features, field):
    values = (value for feature in features
              for value in feature["resolution"].get(field, ()))
    counts = {}
    for value in values:
        key = value if isinstance(value, str) else "features_with_facts"
        counts[key] = counts.get(key, 0) + 1
    return counts


def require_known_rules(features, rules):
    identifiers = {feature["id"] for feature in features}
    unknown = set(rules) - identifiers
    if unknown:
        raise ValueError(f"Règles engine sans capacité source : {sorted(unknown)}")


def catalogue_gaps(source):
    species = source["races"]
    return {"species_size": sum(not item.get("size") for item in species),
            "species_speed": sum(not item.get("speed") for item in species)}


def revision(bundle):
    payload = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    data = json.dumps(build(source), ensure_ascii=False, indent=2) + "\n"
    TARGET.write_text(data, encoding="utf-8")


if __name__ == "__main__":
    main()

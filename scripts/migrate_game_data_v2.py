import json
import re
import unicodedata
from pathlib import Path

CONFIG_PATH = Path(__file__).parents[1] / "game_data.json"
TIMINGS = {
    "Action": "action",
    "Action bonus": "bonus_action",
    "Réaction": "reaction",
    "Libre": "free",
    "Après repos long": "after_long_rest",
}


def slug(value):
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")


def definitions():
    abilities = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
    return {
        "abilities": [{"id": value} for value in abilities],
        "defenses": [{"id": value} for value in ("physical", "elemental", "spiritual")],
        "damage_types": [{"id": value} for value in ("physical", "elemental", "spiritual", "poison")],
        "rest_types": [{"id": "short_rest"}, {"id": "long_rest"}],
    }


def structured_resource(uses):
    match = re.match(r"^(\d+)\s+(?:fois|charges)\s+par\s+(.+)$", uses, re.IGNORECASE)
    if not match:
        return None
    recoveries = {"repos court": "short_rest", "repos long": "long_rest",
                  "repos au feu": "long_rest"}
    recovery = recoveries.get(match.group(2).casefold())
    return {"maximum": int(match.group(1)), "cost": 1,
            "recovery": [recovery]} if recovery else None


def migrate_active(active, feature_id):
    if active is None:
        return
    active["activation"] = {"type": TIMINGS.get(active["timing"], "special")}
    active["resource"] = structured_resource(active["uses"])
    active["automation"] = {"level": "manual", "effects": []}
    if active["resource"]:
        active["resource"]["id"] = f"{feature_id}.uses"


def migrate_passive(passive):
    if passive is not None:
        passive["automation"] = {"level": "manual", "effects": []}


def migrate_path(path, path_id):
    path["id"] = path_id
    for rank in path["ranks"]:
        feature_id = f"{path_id}.rank-{rank['rank']}"
        rank["id"] = feature_id
        migrate_active(rank["active"], feature_id)
        migrate_passive(rank["passive"])


def migrate_group(items, kind):
    for item in items:
        item_id = f"{kind}.{slug(item['name'])}"
        item["id"] = item_id
        for path in item["paths"]:
            migrate_path(path, f"path.{slug(item['name'])}.{slug(path['name'])}")


def migrate(config):
    config["schema_version"] = "2.0.0"
    config["ruleset"] = {"id": "dnd-manager-homebrew", "name": "Gestionnaire JDR",
                         "version": "1.0.0", "locale": "fr-FR"}
    config["definitions"] = definitions()
    migrate_group(config["classes"], "class")
    migrate_group(config["races"], "species")
    return config


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    CONFIG_PATH.write_text(json.dumps(migrate(config), ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()

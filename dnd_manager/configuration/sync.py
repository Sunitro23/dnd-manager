import json
from pathlib import Path

from dnd_manager.characters.common.rules import adjusted_current_hp, maximum_hp
from dnd_manager.configuration.validation import validate_config

ABILITY_ABBREVIATIONS = {
    "FOR": "strength", "DEX": "dexterity", "CON": "constitution",
    "INT": "intelligence", "SAG": "wisdom", "CHA": "charisma",
}
CLASS_SQL = """
INSERT INTO character_class (
    stable_key, name, hit_die, strength_bonus, dexterity_bonus,
    constitution_bonus, intelligence_bonus, wisdom_bonus, charisma_bonus, configured
) VALUES (
    :stable_key, :name, :hit_die, :strength_bonus, :dexterity_bonus,
    :constitution_bonus, :intelligence_bonus, :wisdom_bonus, :charisma_bonus, 1
) ON CONFLICT DO UPDATE SET
    name = excluded.name, hit_die = excluded.hit_die, strength_bonus = excluded.strength_bonus,
    dexterity_bonus = excluded.dexterity_bonus,
    constitution_bonus = excluded.constitution_bonus,
    intelligence_bonus = excluded.intelligence_bonus,
    wisdom_bonus = excluded.wisdom_bonus, charisma_bonus = excluded.charisma_bonus,
    configured = 1
"""
CLASS_PATH_SQL = """
INSERT INTO class_path (stable_key, class_id, name, abilities, ranks_json, configured)
VALUES (?, ?, ?, ?, ?, 1)
ON CONFLICT DO UPDATE SET
    stable_key = excluded.stable_key, class_id = excluded.class_id, name = excluded.name,
    abilities = excluded.abilities,
    ranks_json = excluded.ranks_json, configured = 1
"""
SPECIES_SQL = """
INSERT INTO species (
    stable_key, name, description, traits, physical_bonus, elemental_bonus,
    spiritual_bonus, configured
) VALUES (:id, :name, '', :particularity, :physical, :elemental, :spiritual, 1)
ON CONFLICT DO UPDATE SET
    stable_key = excluded.stable_key, name = excluded.name,
    description = excluded.description, traits = excluded.traits,
    physical_bonus = excluded.physical_bonus, elemental_bonus = excluded.elemental_bonus,
    spiritual_bonus = excluded.spiritual_bonus, configured = 1
"""
RACIAL_PATH_SQL = """
INSERT INTO racial_path (
    stable_key, species_id, name, abilities, ranks_json, strength_bonus, dexterity_bonus,
    constitution_bonus, intelligence_bonus, wisdom_bonus, charisma_bonus, configured
    , physical_bonus, elemental_bonus, spiritual_bonus
) VALUES (
    :stable_key, :species_id, :name, :abilities, :ranks_json, :strength_bonus, :dexterity_bonus,
    :constitution_bonus, :intelligence_bonus, :wisdom_bonus, :charisma_bonus, 1,
    :physical_bonus, :elemental_bonus, :spiritual_bonus
) ON CONFLICT DO UPDATE SET
    stable_key = excluded.stable_key, species_id = excluded.species_id,
    name = excluded.name, abilities = excluded.abilities,
    ranks_json = excluded.ranks_json,
    strength_bonus = excluded.strength_bonus, dexterity_bonus = excluded.dexterity_bonus,
    constitution_bonus = excluded.constitution_bonus,
    intelligence_bonus = excluded.intelligence_bonus, wisdom_bonus = excluded.wisdom_bonus,
    charisma_bonus = excluded.charisma_bonus, physical_bonus = excluded.physical_bonus,
    elemental_bonus = excluded.elemental_bonus, spiritual_bonus = excluded.spiritual_bonus,
    configured = 1
"""
MIGRATE_BARBARIANS_SQL = """
UPDATE character SET class_id = ?, class_path_id = NULL
WHERE class_id IN (
    SELECT id FROM character_class WHERE name = 'Barbare' AND configured = 0
)
"""
CLEAR_INVALID_RACIAL_PATH_SQL = """
UPDATE character SET racial_path_id = NULL
WHERE racial_path_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM character_rank cr
    WHERE cr.character_id = character.id AND cr.path_type = 'racial'
      AND cr.path_id = character.racial_path_id AND cr.rank = 1
)
"""
CHARACTERS_SQL = """
SELECT c.id, c.level, c.constitution, c.current_hp, c.max_hp, cc.hit_die,
       cc.constitution_bonus AS class_constitution_bonus,
       COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus
FROM character c
JOIN character_class cc ON cc.id = c.class_id
LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
"""


def synchronize(database, config_path):
    config = load_config(config_path)
    disable_catalogues(database)
    sync_classes(database, config["classes"])
    sync_species(database, config["races"])
    refresh_characters(database)


def load_config(config_path):
    content = Path(config_path).read_text(encoding="utf-8")
    return validate_config(json.loads(content))


def disable_catalogues(database):
    for table in ("character_class", "species", "class_path", "racial_path"):
        database.execute(f"UPDATE {table} SET configured = 0")


def sync_classes(database, classes):
    for item in classes:
        sync_class(database, item)
    migrate_barbarians(database)


def sync_class(database, item):
    database.execute(CLASS_SQL, class_values(item))
    class_id = row_id(database, "character_class", item["name"])
    for path in item["paths"]:
        sync_class_path(database, class_id, path)


def class_values(item):
    values = {f"{field}_bonus": 2 if key == item["ability_bonus"] else 0
              for key, field in ABILITY_ABBREVIATIONS.items()}
    return {**item, "stable_key": item["id"], **values}


def row_id(database, table, name):
    return database.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()["id"]


def sync_class_path(database, class_id, path):
    ranks = json.dumps(path["ranks"], ensure_ascii=False)
    database.execute(CLASS_PATH_SQL, (path["id"], class_id, path["name"],
                                     path["abilities"], ranks))


def migrate_barbarians(database):
    chevalier = database.execute(
        "SELECT id FROM character_class WHERE name = 'Chevalier' AND configured = 1"
    ).fetchone()
    if chevalier:
        database.execute(MIGRATE_BARBARIANS_SQL, (chevalier["id"],))


def sync_species(database, species):
    for item in species:
        sync_one_species(database, item)


def sync_one_species(database, item):
    database.execute(SPECIES_SQL, {**item, **item["defenses"]})
    species_id = row_id(database, "species", item["name"])
    for path in item["paths"]:
        sync_racial_path(database, species_id, path)


def sync_racial_path(database, species_id, path):
    values = racial_path_values(species_id, path)
    database.execute(RACIAL_PATH_SQL, values)


def racial_path_values(species_id, path):
    values = {"stable_key": path["id"], "species_id": species_id,
              "name": path["name"], "abilities": path["abilities"]}
    values["ranks_json"] = json.dumps(path["ranks"], ensure_ascii=False)
    defenses = {f"{name}_bonus": value for name, value in path.get("defenses", {}).items()}
    defaults = {f"{name}_bonus": 0 for name in ("physical", "elemental", "spiritual")}
    return {**values, **racial_ability_bonuses(path["abilities"]), **defaults, **defenses}


def racial_ability_bonuses(text):
    bonuses = {f"{field}_bonus": 0 for field in ABILITY_ABBREVIATIONS.values()}
    for part in text.split(","):
        add_ability_bonus(bonuses, part)
    return bonuses


def add_ability_bonus(bonuses, part):
    value, abbreviation = part.strip().split()
    bonuses[f"{ABILITY_ABBREVIATIONS[abbreviation]}_bonus"] = int(value)


def refresh_characters(database):
    database.execute(CLEAR_INVALID_RACIAL_PATH_SQL)
    for character in database.execute(CHARACTERS_SQL).fetchall():
        refresh_character(database, character)
    database.commit()


def refresh_character(database, character):
    new_maximum = character_maximum(character)
    current = adjusted_current_hp(character["current_hp"], character["max_hp"], new_maximum)
    database.execute("UPDATE character SET current_hp = ?, max_hp = ? WHERE id = ?",
                     (current, new_maximum, character["id"]))


def character_maximum(character):
    constitution = (character["constitution"] + character["class_constitution_bonus"]
                    + character["racial_constitution_bonus"])
    return maximum_hp(character["hit_die"], character["level"], constitution)

import json
import re
import sqlite3

from dnd_manager.character_api.contracts import (
    AbilityValue,
    CharacterReference,
    CharacterSnapshot,
    DefenseValue,
    DiceValue,
    EquipmentValue,
    HealthSyncResult,
    ResourceSyncResult,
    ResourceValue,
)
from dnd_manager.characters.common.rules import ability_modifier
from dnd_manager.shared.errors import ConcurrentUpdate, RepositoryUnavailable

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
CHARACTER_SQL = """
SELECT c.*, cc.stable_key AS class_key, s.stable_key AS species_key,
       cp.stable_key AS class_path_key, rp.stable_key AS racial_path_key,
       s.size AS species_size, s.speed AS species_speed,
       cc.strength_bonus AS class_strength, cc.dexterity_bonus AS class_dexterity,
       cc.constitution_bonus AS class_constitution, cc.intelligence_bonus AS class_intelligence,
       cc.wisdom_bonus AS class_wisdom, cc.charisma_bonus AS class_charisma,
       COALESCE(rp.strength_bonus, 0) AS racial_strength,
       COALESCE(rp.dexterity_bonus, 0) AS racial_dexterity,
       COALESCE(rp.constitution_bonus, 0) AS racial_constitution,
       COALESCE(rp.intelligence_bonus, 0) AS racial_intelligence,
       COALESCE(rp.wisdom_bonus, 0) AS racial_wisdom,
       COALESCE(rp.charisma_bonus, 0) AS racial_charisma
       , s.physical_bonus AS species_physical
       , s.elemental_bonus AS species_elemental
       , s.spiritual_bonus AS species_spiritual
       , COALESCE(rp.physical_bonus, 0) AS path_physical
       , COALESCE(rp.elemental_bonus, 0) AS path_elemental
       , COALESCE(rp.spiritual_bonus, 0) AS path_spiritual
FROM character c JOIN character_class cc ON cc.id = c.class_id
JOIN species s ON s.id = c.species_id
LEFT JOIN class_path cp ON cp.id = c.class_path_id
LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
WHERE c.id = ?
"""
EQUIPMENT_SQL = """
SELECT stat, SUM(stat_bonus) AS bonus FROM equipment
WHERE character_id = ? AND equipped = 1 AND item_type = 'accessory'
GROUP BY stat
"""
EQUIPMENT_DEFENSE_SQL = """
SELECT COALESCE(SUM(physical_bonus), 0) AS physical,
       COALESCE(SUM(elemental_bonus), 0) AS elemental,
       COALESCE(SUM(spiritual_bonus), 0) AS spiritual
FROM equipment WHERE character_id = ? AND equipped = 1
"""
EQUIPPED_ITEMS_SQL = """
SELECT id, name, item_type, quantity, slot, damage_dice, damage_type,
       physical_bonus, elemental_bonus, spiritual_bonus,
       stat, stat_bonus, effect
FROM equipment WHERE character_id = ? AND equipped = 1
ORDER BY slot, id
"""
RANKS_SQL = """
SELECT cr.path_type, cr.path_id, cr.rank,
       COALESCE(cau.uses_spent, 0) AS spent
FROM character_rank cr
LEFT JOIN character_action_use cau ON cau.character_id = cr.character_id
 AND cau.path_type = cr.path_type AND cau.path_id = cr.path_id AND cau.rank = cr.rank
WHERE cr.character_id = ?
"""
UPDATE_HEALTH = """
UPDATE character SET current_hp = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE id = ? AND version = ?
"""
LIST_CHARACTERS = """
SELECT id, version, name, character_type FROM character
ORDER BY name COLLATE NOCASE, id
"""
PATH_TABLES = {"class": "class_path", "racial": "racial_path"}
STAT_KEYS = {"FOR": "strength", "DEX": "dexterity", "CON": "constitution",
             "INT": "intelligence", "SAG": "wisdom", "CHA": "charisma"}


class SqliteCharacterExchangeRepository:
    def __init__(self, database):
        self.database = database

    def find(self, character_id):
        try:
            return load_snapshot(self.database, character_id)
        except sqlite3.Error as error:
            raise RepositoryUnavailable("La fiche est temporairement indisponible.") from error

    def list(self):
        try:
            return list_characters(self.database)
        except sqlite3.Error as error:
            raise RepositoryUnavailable("Les fiches sont temporairement indisponibles.") from error

    def sync_health(self, character_id, command):
        try:
            return persist_health(self.database, character_id, command)
        except sqlite3.Error as error:
            self.database.rollback()
            raise RepositoryUnavailable("La fiche est temporairement indisponible.") from error

    def sync_resource(self, character_id, resource_key, command):
        try:
            return persist_resource(self.database, character_id, resource_key, command)
        except sqlite3.Error as error:
            self.database.rollback()
            raise RepositoryUnavailable("La ressource est temporairement indisponible.") from error


def list_characters(database):
    rows = database.execute(LIST_CHARACTERS).fetchall()
    return tuple(CharacterReference(row["id"], row["version"], row["name"],
                                    row["character_type"]) for row in rows)


def load_snapshot(database, character_id):
    row = database.execute(CHARACTER_SQL, (character_id,)).fetchone()
    if row is None:
        return None
    abilities = load_abilities(database, row)
    defenses = load_defenses(database, row, abilities)
    equipment = load_equipment_values(database, character_id)
    feature_ids = load_feature_ids(database, character_id)
    resources = load_resources(database, character_id)
    return CharacterSnapshot(row["id"], row["version"], row["name"], row["character_type"],
                             row["level"], row["class_key"], row["species_key"],
                             row["class_path_key"], row["racial_path_key"],
                             row["species_size"], row["species_speed"],
                             row["current_hp"], row["max_hp"], abilities,
                             defenses, equipment, feature_ids, resources)


def load_abilities(database, character):
    equipment = equipment_bonuses(database, character["id"])
    return tuple(ability_value(character, equipment, key) for key in ABILITIES)


def equipment_bonuses(database, character_id):
    rows = database.execute(EQUIPMENT_SQL, (character_id,)).fetchall()
    return {STAT_KEYS[row["stat"]]: row["bonus"] for row in rows if row["stat"] in STAT_KEYS}


def ability_value(character, equipment, key):
    score = character[key] + character[f"class_{key}"] + character[f"racial_{key}"]
    score += equipment.get(key, 0)
    return AbilityValue(key, score, ability_modifier(score))


def load_defenses(database, character, abilities):
    equipment = database.execute(EQUIPMENT_DEFENSE_SQL, (character["id"],)).fetchone()
    modifiers = {ability.key: ability.modifier for ability in abilities}
    sources = {"physical": "constitution", "elemental": "intelligence",
               "spiritual": "wisdom"}
    return tuple(DefenseValue(key, modifiers[ability] + character[f"species_{key}"]
                             + character[f"path_{key}"]
                             + equipment[key]) for key, ability in sources.items())


def load_equipment_values(database, character_id):
    rows = database.execute(EQUIPPED_ITEMS_SQL, (character_id,)).fetchall()
    return tuple(equipment_value(row) for row in rows)


def equipment_value(row):
    return EquipmentValue(row["id"], row["name"], row["item_type"], row["quantity"],
                          row["slot"], parse_dice(row["damage_dice"]), row["damage_dice"],
                          row["damage_type"] or None, equipment_defenses(row),
                          STAT_KEYS.get(row["stat"]), row["stat_bonus"], row["effect"])


def parse_dice(expression):
    match = re.fullmatch(r"\s*(\d+)d(\d+)\s*", expression, re.IGNORECASE)
    return DiceValue(int(match.group(1)), int(match.group(2))) if match else None


def equipment_defenses(row):
    values = ((key, row[f"{key}_bonus"]) for key in ("physical", "elemental", "spiritual"))
    return tuple(DefenseValue(key, value) for key, value in values if value)


def load_resources(database, character_id):
    rows = database.execute(RANKS_SQL, (character_id,)).fetchall()
    values = (resource_from_rank(database, row) for row in rows)
    return tuple(value for value in values if value is not None)


def load_feature_ids(database, character_id):
    rows = database.execute(RANKS_SQL, (character_id,)).fetchall()
    return tuple(feature_id for row in rows for feature_id in rank_feature_ids(
        load_rank(database, row)))


def rank_feature_ids(rank):
    return tuple(f"{rank['id']}.{mode}" for mode in ("active", "passive") if rank.get(mode))


def resource_from_rank(database, row):
    rank = load_rank(database, row)
    active = rank.get("active") or {}
    resource = active.get("resource")
    if not resource:
        return None
    return ResourceValue(resource["id"], rank["name"], row["spent"], resource["maximum"])


def load_rank(database, row):
    table = PATH_TABLES[row["path_type"]]
    query = f"SELECT ranks_json FROM {table} WHERE id = ?"
    path = database.execute(query, (row["path_id"],)).fetchone()
    return json.loads(path["ranks_json"])[row["rank"] - 1]


def persist_health(database, character_id, command):
    maximum = maximum_health(database, character_id)
    if maximum is None:
        return None
    current = min(command.current_hp, maximum)
    cursor = database.execute(UPDATE_HEALTH, (current, character_id, command.expected_version))
    require_updated(database, cursor)
    return HealthSyncResult(character_id, command.expected_version + 1, current, maximum)


def persist_resource(database, character_id, resource_key, command):
    resource = resource_location(database, character_id, resource_key)
    if resource is None:
        return None
    update_character_version(database, character_id, command.expected_version)
    upsert_resource_spent(database, character_id, resource, command.spent)
    database.commit()
    value = ResourceValue(resource_key, resource["name"], command.spent, resource["maximum"])
    return ResourceSyncResult(character_id, command.expected_version + 1, value)


def resource_location(database, character_id, resource_key):
    rows = database.execute(RANKS_SQL, (character_id,)).fetchall()
    locations = (resource_location_from_rank(database, row, resource_key) for row in rows)
    return next((location for location in locations if location), None)


def resource_location_from_rank(database, row, resource_key):
    rank = load_rank(database, row)
    resource = (rank.get("active") or {}).get("resource")
    if not resource or resource["id"] != resource_key:
        return None
    return {"path_type": row["path_type"], "path_id": row["path_id"], "rank": row["rank"],
            "name": rank["name"], "maximum": resource["maximum"]}


def update_character_version(database, character_id, expected_version):
    query = "UPDATE character SET version = version + 1, updated_at = CURRENT_TIMESTAMP "
    cursor = database.execute(query + "WHERE id = ? AND version = ?",
                              (character_id, expected_version))
    require_updated(database, cursor)


def upsert_resource_spent(database, character_id, resource, spent):
    query = """
    INSERT INTO character_action_use
        (character_id, path_type, path_id, rank, uses_spent)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(character_id, path_type, path_id, rank)
    DO UPDATE SET uses_spent = excluded.uses_spent
    """
    database.execute(query, (character_id, resource["path_type"], resource["path_id"],
                             resource["rank"], spent))


def maximum_health(database, character_id):
    row = database.execute("SELECT max_hp FROM character WHERE id = ?", (character_id,)).fetchone()
    return row["max_hp"] if row else None


def require_updated(database, cursor):
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("La fiche a été modifiée depuis sa dernière lecture.")
    database.commit()

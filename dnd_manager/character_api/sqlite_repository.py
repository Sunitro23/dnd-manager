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
    ResistanceValue,
    ResourceSyncResult,
    ResourceValue,
)
from dnd_manager.characters.common.rules import ability_modifier
from dnd_manager.shared.catalog import ABILITY_ABBREVIATIONS, ABILITY_FIELDS
from dnd_manager.shared.errors import ConcurrentUpdate, InvalidRequest, RepositoryUnavailable

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
WHERE c.id = ? {visibility}
"""
CAMPAIGN_ONLY = "AND c.visibility = 'campaign'"
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
RESISTANCES_SQL = """
SELECT damage_type, level, source
FROM character_resistance
WHERE character_id = ?
ORDER BY damage_type, level
"""
UPDATE_HEALTH = """
UPDATE character SET current_hp = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE id = ? AND version = ?
"""
LIST_CHARACTERS = """
SELECT id, version, name, character_type FROM character
{visibility} ORDER BY name COLLATE NOCASE, id
"""


class SqliteCharacterExchangeRepository:
    """`public_only` reproduit la règle de visibilité de l'interface web : sans cette
    restriction, l'API exposait les personnages réservés au MJ."""

    def __init__(self, database, public_only=True):
        self.database = database
        self.public_only = public_only

    def find(self, character_id):
        try:
            return load_snapshot(self.database, character_id, self.public_only)
        except sqlite3.Error as error:
            raise RepositoryUnavailable("La fiche est temporairement indisponible.") from error

    def list(self):
        try:
            return list_characters(self.database, self.public_only)
        except sqlite3.Error as error:
            raise RepositoryUnavailable("Les fiches sont temporairement indisponibles.") from error

    def sync_health(self, character_id, command):
        try:
            return persist_health(self.database, character_id, command, self.public_only)
        except sqlite3.Error as error:
            self.database.rollback()
            raise RepositoryUnavailable("La fiche est temporairement indisponible.") from error

    def sync_resource(self, character_id, resource_key, command):
        try:
            return persist_resource(self.database, character_id, resource_key, command,
                                    self.public_only)
        except sqlite3.Error as error:
            self.database.rollback()
            raise RepositoryUnavailable("La ressource est temporairement indisponible.") from error


def visibility_clause(public_only):
    return CAMPAIGN_ONLY if public_only else ""


def list_characters(database, public_only):
    query = LIST_CHARACTERS.format(
        visibility="WHERE visibility = 'campaign'" if public_only else "")
    rows = database.execute(query).fetchall()
    return tuple(CharacterReference(row["id"], row["version"], row["name"],
                                    row["character_type"]) for row in rows)


def load_snapshot(database, character_id, public_only=True):
    query = CHARACTER_SQL.format(visibility=visibility_clause(public_only))
    row = database.execute(query, (character_id,)).fetchone()
    if row is None:
        return None
    abilities = load_abilities(database, row)
    defenses = load_defenses(database, row, abilities)
    equipment = load_equipment_values(database, character_id)
    ranks = load_unlocked_ranks(database, character_id)
    return CharacterSnapshot(row["id"], row["version"], row["name"], row["character_type"],
                             row["level"], row["class_key"], row["species_key"],
                             row["class_path_key"], row["racial_path_key"],
                             row["species_size"], row["species_speed"],
                             row["current_hp"], row["max_hp"], abilities,
                             defenses, equipment, feature_ids(ranks), resources(ranks))


def load_abilities(database, character):
    equipment = equipment_bonuses(database, character["id"])
    return tuple(ability_value(character, equipment, key) for key in ABILITY_FIELDS)


def equipment_bonuses(database, character_id):
    rows = database.execute(EQUIPMENT_SQL, (character_id,)).fetchall()
    return {ABILITY_ABBREVIATIONS[row["stat"]]: row["bonus"] for row in rows if row["stat"] in ABILITY_ABBREVIATIONS}


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
                          ABILITY_ABBREVIATIONS.get(row["stat"]), row["stat_bonus"], row["effect"])


def parse_dice(expression):
    match = re.fullmatch(r"\s*(\d+)d(\d+)\s*", expression, re.IGNORECASE)
    return DiceValue(int(match.group(1)), int(match.group(2))) if match else None


def equipment_defenses(row):
    values = ((key, row[f"{key}_bonus"]) for key in ("physical", "elemental", "spiritual"))
    return tuple(DefenseValue(key, value) for key, value in values if value)


def load_resistances(database, character_id):
    rows = database.execute(RESISTANCES_SQL, (character_id,)).fetchall()
    return tuple(ResistanceValue(row["damage_type"], row["level"]) for row in rows)


def load_unlocked_ranks(database, character_id):
    """Un seul parcours des rangs : les définitions de voies sont lues une fois chacune.

    Les deux projections (capacités et ressources) reposaient auparavant sur une requête
    par rang, chacune reparsant le JSON complet de la voie.
    """
    rows = database.execute(RANKS_SQL, (character_id,)).fetchall()
    definitions = path_definitions(database, rows)
    return tuple((row, rank_definition(definitions, row)) for row in rows)


def path_definitions(database, rows):
    keys = {(row["path_type"], row["path_id"]) for row in rows}
    return {key: canonical_ranks(database, key) for key in keys}


def canonical_ranks(database, key):
    path_type, path_id = key
    query = (
        "SELECT pd.stable_key AS path_key, pr.rank, pr.name, "
        "pc.stable_key AS capability_key, pc.execution_mode, "
        "pc.uses_maximum, pc.recharge "
        "FROM path_definition pd JOIN path_rank pr ON pr.path_definition_id=pd.id "
        "LEFT JOIN path_capability pc ON pc.path_rank_id=pr.id "
        "WHERE pd.origin_type=? AND pd.legacy_path_id=? "
        "ORDER BY pr.rank, pc.position, pc.id"
    )
    rows = database.execute(query, (path_type, path_id)).fetchall()
    if not rows:
        from dnd_manager.paths.repository import migrate_missing_legacy_paths
        owner_table = "class_path" if path_type == "class" else "racial_path"
        owner_column = "class_id" if path_type == "class" else "species_id"
        owner = database.execute(
            f"SELECT {owner_column} FROM {owner_table} WHERE id=?", (path_id,),
        ).fetchone()
        if owner:
            migrate_missing_legacy_paths(database, path_type, owner[owner_column])
            rows = database.execute(query, (path_type, path_id)).fetchall()
    if not rows:
        raise InvalidRequest("Une voie débloquée ne figure plus au catalogue de règles.")
    ranks = {}
    for item in rows:
        rank = ranks.setdefault(item["rank"], {
            "id": f"{item['path_key']}.rank-{item['rank']}", "rank": item["rank"],
            "name": item["name"], "active": None, "passive": None,
            "capability_ids": [],
        })
        if item["capability_key"] is None:
            continue
        rank["capability_ids"].append(item["capability_key"])
        mode = "passive" if item["execution_mode"] == "permanent" else "active"
        detail = {}
        if mode == "active" and item["uses_maximum"]:
            detail["resource"] = {
                "id": f"{item['capability_key']}.uses",
                "maximum": item["uses_maximum"], "recovery": [item["recharge"]],
            }
        rank[mode] = rank[mode] or detail
    return ranks


def rank_definition(definitions, row):
    ranks = definitions[(row["path_type"], row["path_id"])]
    if row["rank"] not in ranks:
        raise InvalidRequest("Un rang débloqué ne figure plus au catalogue de règles.")
    return ranks[row["rank"]]


def resources(ranks):
    values = (resource_value(row, rank) for row, rank in ranks)
    return tuple(value for value in values if value is not None)


def feature_ids(ranks):
    return tuple(feature_id for _row, rank in ranks for feature_id in rank_feature_ids(rank))


def rank_feature_ids(rank):
    if "capability_ids" in rank:
        return tuple(rank["capability_ids"])
    return tuple(f"{rank['id']}.{mode}" for mode in ("active", "passive") if rank.get(mode))


def resource_value(row, rank):
    resource = (rank.get("active") or {}).get("resource")
    if not resource:
        return None
    return ResourceValue(resource["id"], rank["name"], row["spent"], resource["maximum"])


def persist_health(database, character_id, command, public_only=True):
    maximum = maximum_health(database, character_id, public_only)
    if maximum is None:
        return None
    current = min(command.current_hp, maximum)
    require_updated(database, database.execute(
        UPDATE_HEALTH, (current, character_id, command.expected_version)))
    database.commit()
    return HealthSyncResult(character_id, command.expected_version + 1, current, maximum)


def persist_resource(database, character_id, resource_key, command, public_only=True):
    resource = resource_location(database, character_id, resource_key, public_only)
    if resource is None:
        return None
    # Un seul commit : la version et la dépense doivent progresser ensemble.
    update_character_version(database, character_id, command.expected_version)
    upsert_resource_spent(database, character_id, resource, command.spent)
    database.commit()
    value = ResourceValue(resource_key, resource["name"], command.spent, resource["maximum"])
    return ResourceSyncResult(character_id, command.expected_version + 1, value)


def resource_location(database, character_id, resource_key, public_only=True):
    if not character_is_visible(database, character_id, public_only):
        return None
    locations = (resource_location_of(row, rank, resource_key)
                 for row, rank in load_unlocked_ranks(database, character_id))
    return next((location for location in locations if location), None)


def resource_location_of(row, rank, resource_key):
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


def maximum_health(database, character_id, public_only=True):
    visibility = "AND visibility = 'campaign'" if public_only else ""
    row = database.execute(
        f"SELECT max_hp FROM character WHERE id = ? {visibility}", (character_id,)).fetchone()
    return row["max_hp"] if row else None


def character_is_visible(database, character_id, public_only):
    visibility = "AND visibility = 'campaign'" if public_only else ""
    query = f"SELECT 1 FROM character WHERE id = ? {visibility}"
    return database.execute(query, (character_id,)).fetchone() is not None


def require_updated(database, cursor):
    """Ne valide pas la transaction : l'appelant décide du point de commit."""
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("La fiche a été modifiée depuis sa dernière lecture.")

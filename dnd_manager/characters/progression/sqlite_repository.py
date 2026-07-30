import json
import sqlite3

from dnd_manager.automation.compiler import compile_effect
from dnd_manager.characters.common.constitution import (
    CONSTITUTION_BONUS_COLUMNS,
    accessory_constitution,
    accessory_constitution_column,
    effective_constitution,
)
from dnd_manager.characters.common.rules import ability_modifier
from dnd_manager.characters.progression.contracts import (
    ActionState,
    ProgressionState,
    RacialBonusState,
    RankState,
)
from dnd_manager.shared.errors import ConcurrentUpdate, InvalidRequest, RepositoryUnavailable

FIND_PROGRESSION = f"""
SELECT c.id, c.level, c.current_hp, c.max_hp, c.constitution, c.version,
       cc.hit_die, cc.constitution_bonus AS class_constitution_bonus,
       COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus,
       {accessory_constitution_column()}
FROM character c JOIN character_class cc ON cc.id = c.class_id
LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
WHERE c.id = ? {{visibility}}
"""
UPDATE_LEVEL = """
UPDATE character SET level = ?, current_hp = ?, max_hp = ?,
    version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE id = ? AND version = ?
"""
INSERT_RANK = """
INSERT INTO character_rank (character_id, path_type, path_id, rank)
SELECT ?, ?, ?, ? WHERE
    (SELECT COUNT(*) FROM character_rank WHERE character_id = ?)
    < (SELECT level FROM character WHERE id = ?)
"""
USE_ACTION = """
INSERT INTO character_action_use (character_id, path_type, path_id, rank, uses_spent)
VALUES (?, ?, ?, ?, 1)
ON CONFLICT(character_id, path_type, path_id, rank)
DO UPDATE SET uses_spent = uses_spent + 1 WHERE uses_spent = ?
"""
UPDATE_ACTION_HEALTH = """
UPDATE character SET current_hp = ?, version = version + 1,
    updated_at = CURRENT_TIMESTAMP WHERE id = ?
"""
UPDATE_RACIAL_BONUS = """
UPDATE character SET racial_path_id = ?, current_hp = ?, max_hp = ?,
    version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE id = ? AND version = ?
"""
PATHS = {"class": ("class_path", "class_id"), "racial": ("racial_path", "species_id")}


class SqliteProgressionRepository:
    def __init__(self, database):
        self.database = database

    def find(self, character_id, public_only):
        row = self.database.execute(find_query(public_only), (character_id,)).fetchone()
        return progression_state(row)

    def save_level(self, state, result):
        try:
            self.persist_level(state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def find_rank(self, character_id, public_only, command):
        character = find_character(self.database, character_id, public_only)
        return rank_state(self.database, character, command)

    def save_rank(self, state, result):
        try:
            persist_rank(self.database, state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def find_action(self, character_id, public_only, command):
        try:
            return load_action(self.database, character_id, public_only, command)
        except sqlite3.Error as error:
            self.fail(error)
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            # Catalogue de règles incohérent : ce n'est pas une panne de stockage.
            self.database.rollback()
            raise InvalidRequest("Le catalogue de règles est incohérent "
                                 "pour cette compétence.") from error

    def save_action(self, state, result):
        try:
            persist_action(self.database, state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def find_racial_bonus(self, character_id, public_only, command):
        try:
            return load_racial_bonus(self.database, character_id, public_only, command)
        except sqlite3.Error as error:
            self.fail(error)

    def save_racial_bonus(self, state, result):
        try:
            persist_racial_bonus(self.database, state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def persist_level(self, state, result):
        values = (result.level, result.current_hp, result.maximum_hp,
                  state.character_id, state.version)
        commit_update(self.database, self.database.execute(UPDATE_LEVEL, values))

    def fail(self, error):
        self.database.rollback()
        raise RepositoryUnavailable("Le stockage de la progression est indisponible.") from error


def find_query(public_only):
    visibility = "AND c.visibility = 'campaign'" if public_only else ""
    return FIND_PROGRESSION.format(visibility=visibility)


def progression_state(row):
    if row is None:
        return None
    bonus = sum(row[column] for column in CONSTITUTION_BONUS_COLUMNS)
    return ProgressionState(row["id"], row["level"], row["current_hp"], row["max_hp"],
                            row["constitution"], row["hit_die"], bonus, row["version"])


def commit_update(database, cursor):
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("La fiche a été modifiée simultanément. Recharge la page.")
    database.commit()


def find_character(database, character_id, public_only):
    visibility = "AND visibility = 'campaign'" if public_only else ""
    query = f"SELECT id, level, class_id, species_id FROM character WHERE id = ? {visibility}"
    return database.execute(query, (character_id,)).fetchone()


def rank_state(database, character, command):
    if character is None:
        return None
    return RankState(character["id"], character["level"], spent_points(database, character["id"]),
                     next_rank_number(database, character["id"], command),
                     path_available(database, character, command))


def spent_points(database, character_id):
    query = "SELECT COUNT(*) FROM character_rank WHERE character_id = ?"
    return database.execute(query, (character_id,)).fetchone()[0]


def next_rank_number(database, character_id, command):
    query = ("SELECT COALESCE(MAX(rank), 0) + 1 FROM character_rank "
             "WHERE character_id = ? AND path_type = ? AND path_id = ?")
    return database.execute(query, (character_id, command.path_type, command.path_id)).fetchone()[0]


def path_available(database, character, command):
    table, owner_column = PATHS[command.path_type]
    query = f"SELECT 1 FROM {table} WHERE id = ? AND {owner_column} = ? AND configured = 1"
    return database.execute(query, (command.path_id, character[owner_column])).fetchone() is not None


def persist_rank(database, state, result):
    values = (state.character_id, result.path_type, result.path_id, result.rank,
              state.character_id, state.character_id)
    cursor = database.execute(INSERT_RANK, values)
    commit_rank(database, cursor)


def commit_rank(database, cursor):
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("Les points de voie ont été utilisés simultanément.")
    database.commit()


def load_action(database, character_id, public_only, command):
    character = find_action_character(database, character_id, public_only)
    if character is None:
        return None
    path = find_action_path(database, character, command)
    return action_state(database, character, command, path)


def find_action_character(database, character_id, public_only):
    visibility = "AND c.visibility = 'campaign'" if public_only else ""
    query = ("SELECT c.*, cc.constitution_bonus AS class_constitution_bonus, "
             "COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus, "
             f"{accessory_constitution_column()} FROM character c "
             "JOIN character_class cc ON cc.id = c.class_id "
             f"LEFT JOIN racial_path rp ON rp.id = c.racial_path_id WHERE c.id = ? {visibility}")
    return database.execute(query, (character_id,)).fetchone()


def find_action_path(database, character, command):
    table, owner_column = PATHS[command.path_type]
    query = f"SELECT ranks_json FROM {table} WHERE id = ? AND {owner_column} = ? AND configured = 1"
    return database.execute(query, (command.path_id, character[owner_column])).fetchone()


def action_state(database, character, command, path):
    character_id = character["id"]
    if path is None or not action_unlocked(database, character_id, command):
        return ActionState(character_id, "", "", 0, False)
    rank = rank_definition(path["ranks_json"], command.rank)
    active = rank.get("active") or {}
    resource = active.get("resource") or {}
    return ActionState(character_id, rank["name"], active.get("uses", ""),
                       action_spent(database, character_id, command), True,
                       resource.get("maximum"), character["current_hp"], character["max_hp"],
                       action_modifiers(character), compiled_effects(active))


def rank_definition(serialized_ranks, rank_number):
    ranks = json.loads(serialized_ranks)
    if not 1 <= rank_number <= len(ranks):
        raise InvalidRequest("Cette capacité ne figure pas au catalogue de règles.")
    return ranks[rank_number - 1]


def action_modifiers(character):
    return (("constitution", ability_modifier(effective_constitution(character))),)


def compiled_effects(active):
    specifications = (active.get("automation") or {}).get("effects", ())
    return tuple(compile_effect(specification) for specification in specifications)


def action_unlocked(database, character_id, command):
    query = ("SELECT 1 FROM character_rank WHERE character_id = ? "
             "AND path_type = ? AND path_id = ? AND rank = ?")
    values = (character_id, command.path_type, command.path_id, command.rank)
    return database.execute(query, values).fetchone() is not None


def action_spent(database, character_id, command):
    query = ("SELECT uses_spent FROM character_action_use WHERE character_id = ? "
             "AND path_type = ? AND path_id = ? AND rank = ?")
    values = (character_id, command.path_type, command.path_id, command.rank)
    row = database.execute(query, values).fetchone()
    return row["uses_spent"] if row else 0


def persist_action(database, state, result):
    values = (state.character_id, result.path_type, result.path_id, result.rank, state.spent)
    cursor = database.execute(USE_ACTION, values)
    persist_automated_health(database, result)
    commit_action(database, cursor)


def persist_automated_health(database, result):
    if result.automated:
        database.execute(UPDATE_ACTION_HEALTH, (result.current_hp, result.character_id))


def commit_action(database, cursor):
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("Cette utilisation a déjà été consommée.")
    database.commit()


def load_racial_bonus(database, character_id, public_only, command):
    character = find_bonus_character(database, character_id, public_only)
    if character is None:
        return None
    path = find_racial_path(database, character, command.path_id)
    return racial_bonus_state(database, character, path, command.path_id)


def find_bonus_character(database, character_id, public_only):
    visibility = "AND c.visibility = 'campaign'" if public_only else ""
    query = ("SELECT c.*, cc.hit_die, cc.constitution_bonus AS class_bonus "
             "FROM character c JOIN character_class cc ON cc.id = c.class_id "
             f"WHERE c.id = ? {visibility}")
    return database.execute(query, (character_id,)).fetchone()


def find_racial_path(database, character, path_id):
    query = ("SELECT name, constitution_bonus FROM racial_path "
             "WHERE id = ? AND species_id = ? AND configured = 1")
    return database.execute(query, (path_id, character["species_id"])).fetchone()


def racial_bonus_state(database, character, path, path_id):
    available = path is not None
    bonus = character["class_bonus"] + (path["constitution_bonus"] if available else 0)
    bonus += accessory_constitution(database, character["id"])
    return RacialBonusState(character["id"], path["name"] if available else "",
                            character["level"], character["current_hp"], character["max_hp"],
                            character["constitution"], character["hit_die"], bonus,
                            character["version"], available,
                            racial_rank_unlocked(database, character["id"], path_id))


def racial_rank_unlocked(database, character_id, path_id):
    query = ("SELECT 1 FROM character_rank WHERE character_id = ? "
             "AND path_type = 'racial' AND path_id = ? AND rank = 1")
    return database.execute(query, (character_id, path_id)).fetchone() is not None


def persist_racial_bonus(database, state, result):
    values = (result.path_id, result.current_hp, result.maximum_hp,
              state.character_id, state.version)
    commit_update(database, database.execute(UPDATE_RACIAL_BONUS, values))

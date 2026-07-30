import sqlite3

from dnd_manager.characters.health.contracts import HealthState
from dnd_manager.shared.errors import ConcurrentUpdate, RepositoryUnavailable

UPDATE_HEALTH = """
UPDATE character SET current_hp = ?, estus_available = ?,
    version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE id = ? AND version = ?
"""


class SqliteHealthRepository:
    def __init__(self, database):
        self.database = database

    def find(self, character_id, public_only):
        row = self.database.execute(find_query(public_only), (character_id,)).fetchone()
        return health_state(row)

    def save(self, state, result):
        try:
            self.persist(state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def persist(self, state, result):
        reset_uses(self.database, result)
        cursor = update_health(self.database, state, result)
        commit_update(self.database, cursor)

    def fail(self, error):
        self.database.rollback()
        raise RepositoryUnavailable("Le stockage des PV est indisponible.") from error


def find_query(public_only):
    visibility = "AND visibility = 'campaign'" if public_only else ""
    return f"SELECT id, current_hp, max_hp, estus_available, version FROM character WHERE id = ? {visibility}"


def health_state(row):
    if row is None:
        return None
    return HealthState(row["id"], row["current_hp"], row["max_hp"],
                       bool(row["estus_available"]), row["version"])


def reset_uses(database, result):
    if result.refresh_sheet:
        database.execute("DELETE FROM character_action_use WHERE character_id = ?",
                         (result.character_id,))


def update_health(database, state, result):
    values = (result.current, result.estus_available, state.character_id, state.version)
    return database.execute(UPDATE_HEALTH, values)


def commit_update(database, cursor):
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("La fiche a été modifiée simultanément. Recharge la page.")
    database.commit()

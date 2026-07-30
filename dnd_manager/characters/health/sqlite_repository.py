import sqlite3

from dnd_manager.characters.common.profile import load_profile
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
        profile = load_profile(self.database, character_id, not public_only)
        return health_state(profile)

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


def health_state(profile):
    if profile is None:
        return None
    character = profile.character
    return HealthState(character["id"], character["current_hp"], character["max_hp"],
                       bool(character["estus_available"]), character["version"],
                       tuple(profile.defenses.items()))


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

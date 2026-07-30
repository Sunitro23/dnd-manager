"""Source unique du bonus de Constitution apporté par les accessoires équipés.

Ce calcul entre dans les PV maximums. Il était auparavant recopié dans six requêtes
distinctes, et l'une d'elles l'avait oublié : chaque redémarrage amputait alors les PV
des personnages portant un anneau de Constitution.
"""

ACCESSORY_CONSTITUTION_COLUMN = (
    "COALESCE((SELECT SUM(accessory.stat_bonus) FROM equipment accessory "
    "WHERE accessory.character_id = {character} AND accessory.equipped = 1 "
    "AND accessory.item_type = 'accessory' AND accessory.stat = 'CON'), 0) "
    "AS accessory_constitution_bonus"
)
ACCESSORY_CONSTITUTION_SQL = (
    "SELECT COALESCE(SUM(stat_bonus), 0) FROM equipment WHERE character_id = ? "
    "AND equipped = 1 AND item_type = 'accessory' AND stat = 'CON'"
)
CONSTITUTION_BONUS_COLUMNS = ("class_constitution_bonus", "racial_constitution_bonus",
                              "accessory_constitution_bonus")


def accessory_constitution_column(character="c.id"):
    """Colonne corrélée à agréger dans une requête sur `character`."""
    return ACCESSORY_CONSTITUTION_COLUMN.format(character=character)


def accessory_constitution(database, character_id):
    return database.execute(ACCESSORY_CONSTITUTION_SQL, (character_id,)).fetchone()[0]


def effective_constitution(row):
    """Constitution totale d'une ligne exposant les trois colonnes de bonus."""
    return row["constitution"] + sum(row[column] for column in CONSTITUTION_BONUS_COLUMNS)

import json

from dnd_manager.shared.catalog import ABILITY_ABBREVIATIONS
from dnd_manager.paths.repository import find_path as find_canonical_path, migrate_legacy_path
from dnd_manager.shared.errors import InvalidRequest


PATH_TYPES = {
    "class": {"table": "class_path", "owner_column": "class_id", "owner_label": "classe"},
    "racial": {"table": "racial_path", "owner_column": "species_id", "owner_label": "race"},
}
def path_from_form(form):
    path_type = form.get("path_type", "")
    if path_type not in PATH_TYPES:
        raise InvalidRequest("Choisis un type de voie.")
    name = form.get("name", "").strip()
    if not name or len(name) > 80:
        raise InvalidRequest("Le nom de la voie est obligatoire (80 caractères maximum).")
    owner_id = positive_integer(form.get(f"{PATH_TYPES[path_type]['owner_column']}"))
    abilities = form.get("abilities", "").strip()
    if len(abilities) > 160:
        raise InvalidRequest("Les caractéristiques sont limitées à 160 caractères.")
    return {"path_type": path_type, "name": name, "owner_id": owner_id,
            "abilities": abilities, "ranks": ranks_from_form(form)}


def ranks_from_form(form):
    ranks = []
    for number in range(1, 6):
        name = form.get(f"rank_{number}_name", "").strip()
        if not name:
            raise InvalidRequest(f"Le nom du rang {number} est obligatoire.")
        if len(name) > 100:
            raise InvalidRequest(f"Le rang {number} est trop long.")
        ranks.append({"rank": number, "name": name, "active": None,
                      "passive": None, "capabilities": []})
    return ranks


def positive_integer(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidRequest("Choisis une classe ou une race.") from error
    if number <= 0:
        raise InvalidRequest("Choisis une classe ou une race.")
    return number


def persist_path(database, values, path_id=None):
    definition = PATH_TYPES[values["path_type"]]
    ensure_owner(database, values["path_type"], values["owner_id"])
    ranks_json = json.dumps(values["ranks"], ensure_ascii=False)
    if path_id is None:
        cursor = insert_path(database, definition, values, ranks_json)
        path_id = cursor.lastrowid
        migrate_persisted_path(database, values["path_type"], path_id, refresh=True)
        database.commit()
        return path_id
    update_path(database, definition, values, ranks_json, path_id)
    migrate_persisted_path(database, values["path_type"], path_id)
    database.commit()
    return path_id


def migrate_persisted_path(database, path_type, path_id, refresh=False):
    definition = PATH_TYPES[path_type]
    row = database.execute(
        f"SELECT * FROM {definition['table']} WHERE id = ?", (path_id,)
    ).fetchone()
    migrate_legacy_path(database, path_type, definition["owner_column"], row)
    if refresh:
        canonical = database.execute(
            "SELECT * FROM path_definition WHERE origin_type = ? AND legacy_path_id = ?",
            (path_type, path_id),
        ).fetchone()
        from dnd_manager.paths.normalized import refresh_definition
        refresh_definition(database, canonical)


def ensure_owner(database, path_type, owner_id):
    table = "character_class" if path_type == "class" else "species"
    if database.execute(f"SELECT 1 FROM {table} WHERE id = ? AND configured = 1",
                        (owner_id,)).fetchone() is None:
        raise InvalidRequest("Cette classe ou cette race n’est plus disponible.")


def insert_path(database, definition, values, ranks_json):
    columns = f"{definition['owner_column']}, name, abilities, ranks_json, configured"
    query = f"INSERT INTO {definition['table']} ({columns}) VALUES (?, ?, ?, ?, 1)"
    arguments = (values["owner_id"], values["name"], values["abilities"], ranks_json)
    if values["path_type"] == "racial":
        bonuses = racial_bonuses(values["abilities"])
        bonus_columns = ", ".join(bonuses)
        placeholders = ", ".join("?" for _ in bonuses)
        query = (f"INSERT INTO racial_path ({columns}, {bonus_columns}) "
                 f"VALUES (?, ?, ?, ?, 1, {placeholders})")
        arguments += tuple(bonuses.values())
    return database.execute(query, arguments)


def update_path(database, definition, values, ranks_json, path_id):
    query = (f"UPDATE {definition['table']} SET {definition['owner_column']} = ?, name = ?, "
             "abilities = ?, ranks_json = ?, configured = 1 WHERE id = ?")
    arguments = [values["owner_id"], values["name"], values["abilities"], ranks_json, path_id]
    if values["path_type"] == "racial":
        bonuses = racial_bonuses(values["abilities"])
        assignments = ", ".join(f"{column} = ?" for column in bonuses)
        query = (f"UPDATE racial_path SET species_id = ?, name = ?, abilities = ?, "
                 f"ranks_json = ?, configured = 1, {assignments} WHERE id = ?")
        arguments = [values["owner_id"], values["name"], values["abilities"], ranks_json,
                     *bonuses.values(), path_id]
    cursor = database.execute(query, arguments)
    if cursor.rowcount != 1:
        raise InvalidRequest("Cette voie n’existe plus.")


def racial_bonuses(text):
    bonuses = {f"{field}_bonus": 0 for field in ABILITY_ABBREVIATIONS.values()}
    for part in text.split(","):
        tokens = part.strip().split()
        if len(tokens) == 2 and tokens[0].lstrip("+").isdigit() and tokens[1] in ABILITY_ABBREVIATIONS:
            bonuses[f"{ABILITY_ABBREVIATIONS[tokens[1]]}_bonus"] += int(tokens[0])
    return bonuses


def find_path(database, path_type, path_id):
    if path_type not in PATH_TYPES:
        return None
    return find_canonical_path(database, path_type, path_id)

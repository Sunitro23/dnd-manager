"""Résolution du propriétaire d'un personnage, partagée par la création et l'édition MJ."""


def find_or_create_owner(database, owner_name):
    query = "SELECT id FROM player WHERE display_name = ? COLLATE NOCASE"
    owner = database.execute(query, (owner_name,)).fetchone()
    return owner["id"] if owner else create_owner(database, owner_name)


def create_owner(database, owner_name):
    return database.execute("INSERT INTO player (display_name) VALUES (?)",
                            (owner_name,)).lastrowid

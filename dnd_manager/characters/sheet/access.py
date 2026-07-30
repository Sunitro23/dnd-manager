from flask import abort

from dnd_manager.authentication.http import is_gm
from dnd_manager.infrastructure.database import get_db


def accessible_character(character_id):
    character = find_accessible_character(character_id, is_gm())
    if character is None:
        abort(404)
    return character


def find_accessible_character(character_id, gm_access):
    visibility = "" if gm_access else "AND visibility = 'campaign'"
    query = f"SELECT * FROM character WHERE id = ? {visibility}"
    return get_db().execute(query, (character_id,)).fetchone()

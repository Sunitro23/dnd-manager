from flask import abort

from auth import is_gm
from database import get_db


def accessible_character(character_id):
    visibility_clause = "" if is_gm() else "AND visibility = 'campaign'"
    character = get_db().execute(
        f"""
        SELECT *
        FROM character
        WHERE id = ? {visibility_clause}
        """,
        (character_id,),
    ).fetchone()
    if character is None:
        abort(404)
    return character

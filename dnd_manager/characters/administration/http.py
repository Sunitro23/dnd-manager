import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from dnd_manager.characters.administration.edit import update_character
from dnd_manager.characters.common.constitution import accessory_constitution
from dnd_manager.characters.common.rules import (
    MAXIMUM_ABILITY_SCORE,
    MINIMUM_ABILITY_SCORE,
    POINT_BUY_BUDGET,
)
from dnd_manager.characters.inventory.contracts import EQUIPMENT_COLUMNS
from dnd_manager.characters.inventory.item_form import recalculate_hp
from dnd_manager.authentication.http import gm_required, validate_csrf
from dnd_manager.infrastructure.database import get_db
from dnd_manager.shared.catalog import ABILITY_FIELDS, CHARACTER_TYPES, VISIBILITIES
from dnd_manager.shared.errors import ApplicationError, ConcurrentUpdate

bp = Blueprint("admin", __name__, url_prefix="/mj")

ADMIN_CHARACTER_SQL = """
SELECT c.*, cc.name AS class_name, cc.hit_die,
       cc.strength_bonus AS class_strength_bonus,
       cc.dexterity_bonus AS class_dexterity_bonus,
       cc.constitution_bonus AS class_constitution_bonus,
       cc.intelligence_bonus AS class_intelligence_bonus,
       cc.wisdom_bonus AS class_wisdom_bonus,
       cc.charisma_bonus AS class_charisma_bonus,
       COALESCE(rp.strength_bonus, 0) AS racial_strength_bonus,
       COALESCE(rp.dexterity_bonus, 0) AS racial_dexterity_bonus,
       COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus,
       COALESCE(rp.intelligence_bonus, 0) AS racial_intelligence_bonus,
       COALESCE(rp.wisdom_bonus, 0) AS racial_wisdom_bonus,
       COALESCE(rp.charisma_bonus, 0) AS racial_charisma_bonus,
       p.display_name AS owner_name
FROM character c
JOIN character_class cc ON cc.id = c.class_id
LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
LEFT JOIN player p ON p.id = c.owner_id
WHERE c.id = ?
"""
COPY_CHARACTER_SQL = """
INSERT INTO character (
    campaign_id, owner_id, class_id, species_id, class_path_id, racial_path_id,
    name, character_type, visibility, level, description, personal_info,
    strength, dexterity, constitution, intelligence, wisdom, charisma,
    current_hp, max_hp
)
SELECT campaign_id, NULL, class_id, species_id, class_path_id, racial_path_id,
       ?, character_type, visibility, level, description, personal_info,
       strength, dexterity, constitution, intelligence, wisdom, charisma,
       current_hp, max_hp
FROM character WHERE id = ?
"""
COPY_RANKS_SQL = """
INSERT INTO character_rank (character_id, path_type, path_id, rank)
SELECT ?, path_type, path_id, rank FROM character_rank WHERE character_id = ?
"""
COPY_EQUIPMENT_SQL = (
    f"INSERT INTO equipment (character_id, {', '.join(EQUIPMENT_COLUMNS)}) "
    f"SELECT ?, {', '.join(EQUIPMENT_COLUMNS)} FROM equipment WHERE character_id = ?"
)


def character_for_admin(character_id):
    character = get_db().execute(ADMIN_CHARACTER_SQL, (character_id,)).fetchone()
    if character is None:
        abort(404)
    return character


def submit_character_edit(database, character):
    validate_csrf()
    return attempt_character_edit(database, character)


def attempt_character_edit(database, character):
    try:
        update_character(database, character, request.form)
    except ConcurrentUpdate as error:
        abort(409, str(error))
    except (ApplicationError, ValueError, sqlite3.IntegrityError) as error:
        return rejected_edit(database, error)
    return accepted_edit(character["id"])


def rejected_edit(database, error):
    database.rollback()
    message = "Ce nom de propriétaire existe déjà." if isinstance(
        error, sqlite3.IntegrityError) else str(error)
    flash(message, "error")


def accepted_edit(character_id):
    flash("Personnage mis à jour.", "success")
    return redirect(url_for("main.character_detail", character_id=character_id))


@bp.route("/personnages/<int:character_id>/modifier", methods=("GET", "POST"))
@gm_required
def character_edit(character_id):
    database = get_db()
    character = character_for_admin(character_id)
    options = admin_options(database)
    return EDIT_HANDLERS[request.method](database, character, options)


@bp.post("/personnages/<int:character_id>/supprimer")
@gm_required
def character_delete(character_id):
    validate_csrf()
    database = get_db()
    character = database.execute(
        "SELECT name FROM character WHERE id = ?", (character_id,)
    ).fetchone()
    if character is None:
        abort(404)
    database.execute("DELETE FROM character WHERE id = ?", (character_id,))
    database.commit()
    flash(f"{character['name']} a été supprimé définitivement.", "success")
    return redirect(url_for("main.gm_dashboard"))


def show_character_edit(_database, character, options):
    return render_character_form(character, options)


def post_character_edit(database, character, options):
    response = submit_character_edit(database, character)
    if response:
        return response
    return render_character_form(character_for_admin(character["id"]), options)


EDIT_HANDLERS = {"GET": show_character_edit, "POST": post_character_edit}


def admin_options(database):
    species = database.execute("SELECT id, name FROM species WHERE configured = 1 "
                               "ORDER BY name COLLATE NOCASE").fetchall()
    players = database.execute("SELECT id, display_name FROM player "
                               "ORDER BY display_name COLLATE NOCASE").fetchall()
    return species, players


def render_character_form(character, options):
    species, players = options
    return render_template("admin/character_form.html", character=character, species=species,
                           players=players, character_types=CHARACTER_TYPES,
                           visibilities=VISIBILITIES, abilities=ABILITY_FIELDS,
                           accessory_constitution_bonus=accessory_constitution(
                               get_db(), character["id"]),
                           ability_budget=POINT_BUY_BUDGET,
                           ability_minimum=MINIMUM_ABILITY_SCORE,
                           ability_maximum=MAXIMUM_ABILITY_SCORE)


@bp.post("/personnages/<int:character_id>/dupliquer")
@gm_required
def character_duplicate(character_id):
    validate_csrf()
    return duplicated_response(duplicate_from_id(character_id))


def duplicate_from_id(character_id):
    database = get_db()
    source = character_for_admin(character_id)
    copy_name = f"{source['name'][:68]} — copie"
    return duplicate_character(database, character_id, copy_name)


def duplicated_response(copy_id):
    flash("Personnage dupliqué sans propriétaire.", "success")
    return redirect(url_for("main.character_detail", character_id=copy_id))


def duplicate_character(database, character_id, copy_name):
    cursor = database.execute(COPY_CHARACTER_SQL, (copy_name, character_id))
    copy_id = cursor.lastrowid
    copy_character_relations(database, character_id, copy_id)
    database.commit()
    return copy_id


def copy_character_relations(database, source_id, copy_id):
    database.execute(COPY_RANKS_SQL, (copy_id, source_id))
    database.execute(COPY_EQUIPMENT_SQL, (copy_id, source_id))
    # Les PV copiés tels quels seraient faux si un accessoire modifie la Constitution.
    recalculate_hp(database, copy_id)

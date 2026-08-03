import sqlite3

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from dnd_manager.authentication.http import gm_required, is_gm, validate_csrf
from dnd_manager.characters.common.rules import (
    MAXIMUM_ABILITY_SCORE,
    MINIMUM_ABILITY_SCORE,
    POINT_BUY_BUDGET,
)
from dnd_manager.characters.creation.form import catalogue_options, character_values
from dnd_manager.characters.sheet.presentation import render_character_sheet
from dnd_manager.campaign.path_editor import PATH_TYPES, find_path, path_from_form, persist_path
from dnd_manager.campaign.capability_editor import capability_values
from dnd_manager.infrastructure.database import get_db
from dnd_manager.paths.repository import list_paths
from dnd_manager.paths.normalized import (
    delete_capability, find_capability, save_capability, update_rank_metadata,
)
from dnd_manager.shared.catalog import CHARACTER_TYPES, VISIBILITIES
from dnd_manager.shared.errors import ApplicationError

bp = Blueprint("main", __name__)

GM_CHARACTERS_SQL = """
SELECT c.id, c.name, c.character_type, c.visibility, c.current_hp, c.max_hp,
       c.portrait_filename, p.display_name AS owner_name
FROM character c LEFT JOIN player p ON p.id = c.owner_id
{where_clause} ORDER BY c.visibility, c.name COLLATE NOCASE
"""
PATH_QUERIES = {
    "classes": "SELECT cc.id, cc.name, cc.description, cc.hit_die, "
               "(SELECT COUNT(*) FROM path_definition pd "
               " WHERE pd.origin_type = 'class' AND pd.origin_id = cc.id "
               " AND pd.status = 'published') AS path_count "
               "FROM character_class cc "
               "WHERE configured = 1 ORDER BY name COLLATE NOCASE",
    "races": "SELECT s.id, s.name, s.description, s.traits, "
             "s.physical_bonus, s.elemental_bonus, "
             "s.spiritual_bonus, (SELECT COUNT(*) FROM path_definition pd "
             " WHERE pd.origin_type = 'racial' AND pd.origin_id = s.id "
             " AND pd.status = 'published') AS path_count "
             "FROM species s WHERE configured = 1 ORDER BY name COLLATE NOCASE",
}
CAMPAIGN_CHARACTERS_SQL = """
SELECT c.id, c.name, c.character_type, c.level, c.current_hp, c.max_hp,
       c.portrait_filename, cc.name AS class_name, s.name AS species_name,
       p.display_name AS owner_name
FROM character c
LEFT JOIN character_class cc ON cc.id = c.class_id
LEFT JOIN species s ON s.id = c.species_id
LEFT JOIN player p ON p.id = c.owner_id
WHERE c.visibility = 'campaign'
ORDER BY c.name COLLATE NOCASE
"""


@bp.get("/voies")
def paths_catalog():
    database = get_db()
    context = path_context(database)
    return render_template("paths/index.html", **context)


@bp.route("/mj/voies/nouvelle", methods=("GET", "POST"))
@gm_required
def path_create():
    return path_form_response()


@bp.route("/mj/voies/<path_type>/<int:path_id>/modifier", methods=("GET", "POST"))
@gm_required
def path_edit(path_type, path_id):
    path = find_path(get_db(), path_type, path_id)
    if path is None:
        return ("Voie introuvable.", 404)
    return path_form_response(path, path_id)


@bp.route("/mj/voies/<path_type>/<int:path_id>/rangs/<int:rank>/capacites/nouvelle",
          methods=("GET", "POST"))
@gm_required
def capability_create(path_type, path_id, rank):
    path = find_path(get_db(), path_type, path_id)
    if path is None or not 1 <= rank <= 5:
        return ("Voie ou rang introuvable.", 404)
    return capability_form_response(path, rank)


@bp.route("/mj/voies/<path_type>/<int:path_id>/rangs/<int:rank>/capacites/<int:capability_id>",
          methods=("GET", "POST"))
@gm_required
def capability_edit(path_type, path_id, rank, capability_id):
    path = find_path(get_db(), path_type, path_id)
    if path is None or not 1 <= rank <= 5:
        return ("Voie ou rang introuvable.", 404)
    capability = find_capability(get_db(), path["definition_id"], capability_id)
    if capability is None or capability["rank"] != rank:
        return ("Capacité introuvable.", 404)
    detail = next((item for item in path["ranks"][rank - 1]["capability_details"]
                   if item["id"] == capability_id), None)
    return capability_form_response(path, rank, detail)


@bp.post("/mj/voies/<path_type>/<int:path_id>/capacites/<int:capability_id>/supprimer")
@gm_required
def capability_delete(path_type, path_id, capability_id):
    validate_csrf()
    path = find_path(get_db(), path_type, path_id)
    if path is None or not delete_capability(get_db(), path["definition_id"], capability_id):
        return ("Capacité introuvable.", 404)
    flash("Capacité supprimée.", "success")
    return redirect(url_for("main.path_edit", path_type=path_type, path_id=path_id))


def capability_form_response(path, rank, capability=None):
    if request.method == "POST":
        validate_csrf()
        try:
            values = capability_values(request.form, path["stable_key"])
            capability_id = save_capability(
                get_db(), path["definition_id"], rank, values,
                capability["id"] if capability else None,
            )
            flash("Capacité enregistrée dans le nouveau système.", "success")
            return redirect(url_for(
                "main.capability_edit", path_type=path["path_type"], path_id=path["id"],
                rank=rank, capability_id=capability_id,
            ))
        except (ApplicationError, ValueError, sqlite3.IntegrityError) as error:
            get_db().rollback()
            flash(str(error), "error")
    return render_template("paths/capability_form.html", path=path, rank=rank,
                           capability=capability)


def path_form_response(path=None, path_id=None):
    database = get_db()
    if request.method == "POST":
        validate_csrf()
        try:
            values = path_from_form(request.form)
            if path is not None and values["path_type"] != path["path_type"]:
                raise ApplicationError("Le type d’une voie existante ne peut pas être changé.")
            saved_id = persist_path(database, values, path_id)
            saved_path = find_path(database, values["path_type"], saved_id)
            update_rank_metadata(database, saved_path["definition_id"], values["ranks"], request.form)
            flash("Voie enregistrée.", "success")
            return redirect(url_for("main.path_edit", path_type=values["path_type"],
                                    path_id=saved_id))
        except (ApplicationError, ValueError, sqlite3.IntegrityError) as error:
            database.rollback()
            message = ("Une voie de ce nom existe déjà pour ce choix."
                       if isinstance(error, sqlite3.IntegrityError) else str(error))
            flash(message, "error")
    context = path_context(database)
    return render_template("paths/form.html", path=path, classes=context["classes"],
                           races=context["races"], path_types=PATH_TYPES)


def path_context(database):
    context = {name: database.execute(query).fetchall()
               for name, query in PATH_QUERIES.items() if name in {"classes", "races"}}
    context["class_paths"] = list_paths(database, "class")
    context["racial_paths"] = list_paths(database, "racial")
    return context


@bp.get("/")
def campaign():
    characters = get_db().execute(CAMPAIGN_CHARACTERS_SQL).fetchall()
    grouped = {kind: characters_of_type(characters, kind) for kind in CHARACTER_TYPES}
    return render_template("campaign/index.html", characters=characters,
                           grouped_characters=grouped)


def characters_of_type(characters, character_type):
    return [character for character in characters
            if character["character_type"] == character_type]


@bp.get("/health")
def health():
    get_db().execute("SELECT 1").fetchone()
    return {"status": "ok"}


@bp.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@bp.route("/personnages/nouveau", methods=("GET", "POST"))
def character_create():
    database = get_db()
    options = catalogue_options(database)
    response = {"GET": render_creation, "POST": submit_creation}[request.method](database, options)
    return response or render_creation(database, options)


def submit_creation(database, options):
    validate_csrf()
    try:
        return persist_character(database, options)
    except (ApplicationError, ValueError, sqlite3.IntegrityError) as error:
        return reject_creation(database, error)


def persist_character(database, options):
    require_catalogues(options)
    values = character_values(database, request.form, is_gm())
    character_id = insert_character(database, values)
    flash("Personnage créé.", "success")
    return redirect(url_for("main.character_detail", character_id=character_id, created=1))


def require_catalogues(options):
    classes, species, _players = options
    if not classes or not species:
        raise ValueError("Le MJ doit créer au moins une classe et une espèce.")


def insert_character(database, values):
    columns = ", ".join(values)
    placeholders = ", ".join(f":{key}" for key in values)
    cursor = database.execute(f"INSERT INTO character ({columns}) VALUES ({placeholders})", values)
    database.commit()
    return cursor.lastrowid


def reject_creation(database, error):
    database.rollback()
    message = "Ce nom de joueur est déjà utilisé." if isinstance(
        error, sqlite3.IntegrityError) else str(error)
    flash(message, "error")


def render_creation(_database, options):
    classes, species, players = options
    return render_template("characters/create.html", classes=classes, species=species,
                           players=players, character_types=CHARACTER_TYPES,
                           visibilities=VISIBILITIES, ability_budget=POINT_BUY_BUDGET,
                           ability_minimum=MINIMUM_ABILITY_SCORE,
                           ability_maximum=MAXIMUM_ABILITY_SCORE)


@bp.get("/personnages/<int:character_id>")
def character_detail(character_id):
    return render_character_sheet(character_id)


@bp.get("/mj")
@gm_required
def gm_dashboard():
    database, filters = get_db(), dashboard_filters(request.args)
    characters = filtered_characters(database, filters)
    players = database.execute(
        "SELECT id, display_name FROM player ORDER BY display_name").fetchall()
    return render_dashboard(characters, players, filters)


def render_dashboard(characters, players, filters):
    return render_template("gm/dashboard.html", characters=characters, players=players,
                           filters=filters, character_types=CHARACTER_TYPES,
                           visibilities=VISIBILITIES)


def dashboard_filters(arguments):
    return {"character_type": arguments.get("type", ""),
            "visibility": arguments.get("visibility", ""),
            "owner_id": arguments.get("owner", "")}


def filtered_characters(database, filters):
    clauses = dashboard_clauses(filters)
    conditions = tuple(clause[0] for clause in clauses)
    parameters = tuple(clause[1] for clause in clauses if clause[1] is not None)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return database.execute(GM_CHARACTERS_SQL.format(where_clause=where), parameters).fetchall()


def dashboard_clauses(filters):
    clauses = []
    append_allowed_filter(clauses, "c.character_type", filters["character_type"], CHARACTER_TYPES)
    append_allowed_filter(clauses, "c.visibility", filters["visibility"], VISIBILITIES)
    append_owner_filter(clauses, filters["owner_id"])
    return clauses


def append_allowed_filter(clauses, column, value, allowed):
    if value in allowed:
        clauses.append((f"{column} = ?", value))


def append_owner_filter(clauses, owner_id):
    if owner_id == "none":
        clauses.append(("c.owner_id IS NULL", None))
    if owner_id.isdigit():
        clauses.append(("c.owner_id = ?", int(owner_id)))

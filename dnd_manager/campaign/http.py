import json
import sqlite3

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from dnd_manager.authentication.http import gm_required, is_gm, validate_csrf
from dnd_manager.characters.creation.form import catalogue_options, character_values
from dnd_manager.characters.sheet.presentation import render_character_sheet
from dnd_manager.infrastructure.database import get_db

bp = Blueprint("main", __name__)

CHARACTER_TYPES = ("player", "ally", "npc", "enemy")
VISIBILITIES = ("campaign", "gm")
GM_CHARACTERS_SQL = """
SELECT c.id, c.name, c.character_type, c.visibility, c.current_hp, c.max_hp,
       c.portrait_filename, p.display_name AS owner_name
FROM character c LEFT JOIN player p ON p.id = c.owner_id
{where_clause} ORDER BY c.visibility, c.name COLLATE NOCASE
"""
PATH_QUERIES = {
    "classes": "SELECT id, name, hit_die FROM character_class "
               "WHERE configured = 1 ORDER BY name COLLATE NOCASE",
    "races": "SELECT id, name, traits, physical_bonus, elemental_bonus, spiritual_bonus "
             "FROM species WHERE configured = 1 ORDER BY name COLLATE NOCASE",
    "class_paths": "SELECT * FROM class_path WHERE configured = 1 "
                   "ORDER BY class_id, name COLLATE NOCASE",
    "racial_paths": "SELECT * FROM racial_path WHERE configured = 1 "
                    "ORDER BY species_id, name COLLATE NOCASE",
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
    context = path_context(get_db())
    context["class_paths"] = decoded_paths(context["class_paths"])
    context["racial_paths"] = decoded_paths(context["racial_paths"])
    return render_template("paths/index.html", **context)


def path_context(database):
    return {name: database.execute(query).fetchall()
            for name, query in PATH_QUERIES.items()}


def decoded_paths(paths):
    return [{**dict(path), "ranks": json.loads(path["ranks_json"])} for path in paths]


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
    except (ValueError, sqlite3.IntegrityError) as error:
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
                           visibilities=VISIBILITIES)


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

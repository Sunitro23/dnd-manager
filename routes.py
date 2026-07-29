import json
import re
import sqlite3

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from access import accessible_character
from auth import gm_required, is_gm, validate_csrf
from database import get_db
from rules import (
    ability_modifier,
    defense,
    maximum_hp,
    point_buy_total,
    valid_point_buy,
)

bp = Blueprint("main", __name__)

ABILITY_FIELDS = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)
CHARACTER_TYPES = ("player", "ally", "npc", "enemy")
VISIBILITIES = ("campaign", "gm")


def required_text(name, maximum):
    value = request.form.get(name, "").strip()
    if not value:
        raise ValueError(f'Le champ « {name} » est obligatoire.')
    if len(value) > maximum:
        raise ValueError(f'Le champ « {name} » ne peut pas dépasser {maximum} caractères.')
    return value


def optional_text(name, maximum):
    value = request.form.get(name, "").strip()
    if len(value) > maximum:
        raise ValueError(f'Le champ « {name} » ne peut pas dépasser {maximum} caractères.')
    return value


def catalogue_options(database):
    classes = database.execute(
        """
        SELECT *
        FROM character_class
        WHERE configured = 1
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()
    species_rows = database.execute(
        """
        SELECT id, name
        FROM species
        WHERE configured = 1
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()
    players = database.execute(
        """
        SELECT id, display_name
        FROM player
        ORDER BY display_name COLLATE NOCASE
        """
    ).fetchall()
    return classes, species_rows, players


def catalogue_item(database, table, item_id):
    if table not in {"character_class", "species"}:
        raise ValueError("Catalogue inconnu.")
    item = database.execute(
        f"SELECT * FROM {table} WHERE id = ?", (item_id,)
    ).fetchone()
    if item is None:
        raise ValueError("La classe ou l'espèce sélectionnée n'est plus disponible.")
    return item


def resolve_owner(database):
    owner_name = optional_text("owner_name", 80)
    if not owner_name:
        return None

    owner = database.execute(
        "SELECT id FROM player WHERE display_name = ? COLLATE NOCASE",
        (owner_name,),
    ).fetchone()
    if owner:
        return owner["id"]

    cursor = database.execute(
        "INSERT INTO player (display_name) VALUES (?)",
        (owner_name,),
    )
    return cursor.lastrowid


def character_from_form(database):
    name = required_text("name", 80)
    description = optional_text("description", 4000)
    personal_info = optional_text("personal_info", 4000)

    try:
        class_id = int(request.form.get("class_id", ""))
        species_id = int(request.form.get("species_id", ""))
    except ValueError as error:
        raise ValueError("Une classe et une espèce sont obligatoires.") from error

    class_item = catalogue_item(database, "character_class", class_id)
    catalogue_item(database, "species", species_id)
    racial_path_id = None
    racial_path = None

    scores = {}
    try:
        for field in ABILITY_FIELDS:
            scores[field] = int(request.form.get(field, ""))
    except ValueError as error:
        raise ValueError("Les six caractéristiques doivent être renseignées.") from error

    if not valid_point_buy(scores.values()):
        spent = point_buy_total(scores.values())
        raise ValueError(
            f"Les caractéristiques doivent utiliser exactement 27 points (total actuel : {spent})."
        )

    if is_gm():
        character_type = request.form.get("character_type", "")
        visibility = request.form.get("visibility", "")
        try:
            level = int(request.form.get("level", "1"))
        except ValueError as error:
            raise ValueError("Le niveau doit être un nombre entier.") from error
        if character_type not in CHARACTER_TYPES:
            raise ValueError("Type de personnage invalide.")
        if visibility not in VISIBILITIES:
            raise ValueError("Visibilité invalide.")
        if not 1 <= level <= 20:
            raise ValueError("Le niveau doit être compris entre 1 et 20.")
    else:
        character_type = "player"
        visibility = "campaign"
        level = 1

    owner_id = resolve_owner(database)
    max_hp = maximum_hp(
        class_item["hit_die"],
        level,
        scores["constitution"]
        + class_item["constitution_bonus"]
        + (racial_path["constitution_bonus"] if racial_path else 0),
    )

    return {
        "owner_id": owner_id,
        "class_id": class_id,
        "species_id": species_id,
        "class_path_id": None,
        "racial_path_id": racial_path_id,
        "name": name,
        "character_type": character_type,
        "visibility": visibility,
        "level": level,
        "description": description,
        "personal_info": personal_info,
        **scores,
        "current_hp": max_hp,
        "max_hp": max_hp,
    }


@bp.get("/voies")
def paths_catalog():
    database = get_db()
    classes = database.execute(
        """
        SELECT id, name, hit_die
        FROM character_class
        WHERE configured = 1
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()
    races = database.execute(
        """
        SELECT id, name, traits, physical_bonus, elemental_bonus, spiritual_bonus
        FROM species
        WHERE configured = 1
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()
    class_paths = database.execute(
        """
        SELECT * FROM class_path
        WHERE configured = 1
        ORDER BY class_id, name COLLATE NOCASE
        """
    ).fetchall()
    racial_paths = database.execute(
        """
        SELECT * FROM racial_path
        WHERE configured = 1
        ORDER BY species_id, name COLLATE NOCASE
        """
    ).fetchall()
    return render_template(
        "paths/index.html",
        classes=classes,
        races=races,
        class_paths=[
            {**dict(path), "ranks": json.loads(path["ranks_json"])}
            for path in class_paths
        ],
        racial_paths=[
            {**dict(path), "ranks": json.loads(path["ranks_json"])}
            for path in racial_paths
        ],
    )


@bp.get("/")
def campaign():
    characters = get_db().execute(
        """
        SELECT
            c.id, c.name, c.character_type, c.level,
            c.current_hp, c.max_hp, c.portrait_filename,
            cc.name AS class_name,
            s.name AS species_name,
            p.display_name AS owner_name
        FROM character c
        LEFT JOIN character_class cc ON cc.id = c.class_id
        LEFT JOIN species s ON s.id = c.species_id
        LEFT JOIN player p ON p.id = c.owner_id
        WHERE c.visibility = 'campaign'
        ORDER BY c.name COLLATE NOCASE
        """
    ).fetchall()
    grouped_characters = {
        character_type: [
            character
            for character in characters
            if character["character_type"] == character_type
        ]
        for character_type in CHARACTER_TYPES
    }
    return render_template(
        "campaign/index.html",
        characters=characters,
        grouped_characters=grouped_characters,
    )


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
    classes, species_rows, players = catalogue_options(database)

    if request.method == "POST":
        validate_csrf()
        try:
            if not classes or not species_rows:
                raise ValueError(
                    "Le MJ doit créer au moins une classe et une espèce."
                )
            character_values = character_from_form(database)

            columns = ", ".join(character_values)
            placeholders = ", ".join(f":{key}" for key in character_values)
            cursor = database.execute(
                f"INSERT INTO character ({columns}) VALUES ({placeholders})",
                character_values,
            )
            character_id = cursor.lastrowid
            database.commit()
        except (ValueError, sqlite3.IntegrityError) as error:
            database.rollback()
            message = (
                "Ce nom de joueur est déjà utilisé."
                if isinstance(error, sqlite3.IntegrityError)
                else str(error)
            )
            flash(message, "error")
        else:
            flash("Personnage créé.", "success")
            return redirect(
                url_for(
                    "main.character_detail",
                    character_id=character_id,
                    created=1,
                )
            )

    return render_template(
        "characters/create.html",
        classes=classes,
        species=species_rows,
        players=players,
        character_types=CHARACTER_TYPES,
        visibilities=VISIBILITIES,
    )


@bp.get("/personnages/<int:character_id>")
def character_detail(character_id):
    database = get_db()
    accessible_character(character_id)
    character = database.execute(
        """
        SELECT
            c.*,
            cc.name AS class_name,
            cc.hit_die,
            cc.strength_bonus AS class_strength_bonus,
            cc.dexterity_bonus AS class_dexterity_bonus,
            cc.constitution_bonus AS class_constitution_bonus,
            cc.intelligence_bonus AS class_intelligence_bonus,
            cc.wisdom_bonus AS class_wisdom_bonus,
            cc.charisma_bonus AS class_charisma_bonus,
            rp.name AS racial_bonus_name,
            rp.abilities AS racial_bonus_abilities,
            COALESCE(rp.strength_bonus, 0) AS racial_strength_bonus,
            COALESCE(rp.dexterity_bonus, 0) AS racial_dexterity_bonus,
            COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus,
            COALESCE(rp.intelligence_bonus, 0) AS racial_intelligence_bonus,
            COALESCE(rp.wisdom_bonus, 0) AS racial_wisdom_bonus,
            COALESCE(rp.charisma_bonus, 0) AS racial_charisma_bonus,
            s.name AS species_name,
            s.description AS species_description,
            s.traits AS species_traits,
            s.size AS species_size,
            s.speed AS species_speed,
            s.physical_bonus AS species_physical_bonus,
            s.elemental_bonus AS species_elemental_bonus,
            s.spiritual_bonus AS species_spiritual_bonus,
            p.display_name AS owner_name
        FROM character c
        LEFT JOIN character_class cc ON cc.id = c.class_id
        LEFT JOIN species s ON s.id = c.species_id
        LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
        LEFT JOIN player p ON p.id = c.owner_id
        WHERE c.id = ?
          AND (? = 1 OR c.visibility = 'campaign')
        """,
        (character_id, 1 if is_gm() else 0),
    ).fetchone()

    equipment = database.execute(
        """
        SELECT *
        FROM equipment
        WHERE character_id = ?
        ORDER BY equipped DESC, name COLLATE NOCASE
        """,
        (character_id,),
    ).fetchall()
    paths = []
    for path_type, table, owner_column, owner_id in (
        ("class", "class_path", "class_id", character["class_id"]),
        ("racial", "racial_path", "species_id", character["species_id"]),
    ):
        rows = database.execute(
            f"""
            SELECT * FROM {table}
            WHERE {owner_column} = ? AND configured = 1
            ORDER BY name COLLATE NOCASE
            """,
            (owner_id,),
        ).fetchall()
        paths.extend(
            {
                **dict(path),
                "path_type": path_type,
                "ranks": json.loads(path["ranks_json"]),
            }
            for path in rows
        )
    unlocked_rows = database.execute(
        """
        SELECT path_type, path_id, rank
        FROM character_rank
        WHERE character_id = ?
        """,
        (character_id,),
    ).fetchall()
    unlocked_ranks = {
        f"{path['path_type']}:{path['id']}": {
            row["rank"]
            for row in unlocked_rows
            if row["path_type"] == path["path_type"]
            and row["path_id"] == path["id"]
        }
        for path in paths
    }
    action_uses = {
        (row["path_type"], row["path_id"], row["rank"]): row["uses_spent"]
        for row in database.execute(
            """
            SELECT path_type, path_id, rank, uses_spent
            FROM character_action_use WHERE character_id = ?
            """,
            (character_id,),
        ).fetchall()
    }
    permanent_defense_bonuses = {
        "physical": 0,
        "elemental": 0,
        "spiritual": 0,
    }
    for path in paths:
        path_key = f"{path['path_type']}:{path['id']}"
        for rank in path["ranks"]:
            if rank["rank"] not in unlocked_ranks[path_key]:
                continue
            for defense_name, bonus in rank.get("permanent_bonuses", {}).items():
                field = defense_name.removesuffix("_defense")
                permanent_defense_bonuses[field] += bonus
    available_racial_bonuses = [
        path
        for path in paths
        if path["path_type"] == "racial"
        and 1 in unlocked_ranks[f"racial:{path['id']}"]
    ]
    equipped = [item for item in equipment if item["equipped"]]
    accessory_stat_fields = {
        "FOR": "strength",
        "DEX": "dexterity",
        "CON": "constitution",
        "INT": "intelligence",
        "SAG": "wisdom",
        "CHA": "charisma",
    }
    accessory_ability_bonuses = {field: 0 for field in ABILITY_FIELDS}
    for item in equipped:
        field = accessory_stat_fields.get(item["stat"])
        if item["item_type"] == "accessory" and field:
            accessory_ability_bonuses[field] += item["stat_bonus"]
    effective_scores = {
        field: character[field]
        + character[f"class_{field}_bonus"]
        + character[f"racial_{field}_bonus"]
        + accessory_ability_bonuses[field]
        for field in ABILITY_FIELDS
    }
    modifiers = {
        field: ability_modifier(effective_scores[field]) for field in ABILITY_FIELDS
    }
    modifier_labels = {
        "Force": "strength",
        "Dextérité": "dexterity",
        "Constitution": "constitution",
        "Intelligence": "intelligence",
        "Sagesse": "wisdom",
        "Charisme": "charisma",
    }

    def personalized_effect(effect):
        for label, field in modifier_labels.items():
            modifier = modifiers[field]
            signed = f"+ {modifier}" if modifier >= 0 else f"- {abs(modifier)}"
            effect = effect.replace(f"+ MOD {label}", signed)
            effect = effect.replace(f"MOD {label}", f"{modifier:+d}")
        return effect

    def personalized_uses(uses):
        for count in (1, 2, 3):
            uses = uses.replace(
                f"{count} fois par Repos au Feu",
                f"{count} utilisation{'s' if count > 1 else ''} avant repos",
            )
        return uses.replace(
            "3 charges par Repos au Feu", "3 charges avant repos"
        )

    available_actions = []
    available_passives = []
    for path in paths:
        path_key = f"{path['path_type']}:{path['id']}"
        for rank in path["ranks"]:
            active = rank.get("active")
            passive = rank.get("passive")
            rank["_active_effect"] = (
                personalized_effect(active["effect"]) if active else None
            )
            rank["_active_uses"] = personalized_uses(active["uses"]) if active else None
            rank["_passive_effect"] = (
                personalized_effect(passive["effect"]) if passive else None
            )
            if rank["rank"] not in unlocked_ranks[path_key]:
                continue
            if active:
                uses_match = re.match(
                    r"^(\d+)\s+(?:fois|charges)\b",
                    active["uses"],
                    re.IGNORECASE,
                )
                uses_limit = int(uses_match.group(1)) if uses_match else None
                uses_spent = action_uses.get(
                    (path["path_type"], path["id"], rank["rank"]), 0
                )
                available_actions.append(
                    {
                        "key": (
                            f"{path['path_type']}:{path['id']}:{rank['rank']}"
                        ),
                        "path_type": path["path_type"],
                        "path_id": path["id"],
                        "rank": rank["rank"],
                        "category": "Compétences",
                        "source": path["name"],
                        "name": rank["name"],
                        "timing": active["timing"],
                        "uses": (
                            f"{max(0, uses_limit - uses_spent)}/{uses_limit} restantes"
                            if uses_limit is not None
                            else rank["_active_uses"]
                        ),
                        "remaining": (
                            max(0, uses_limit - uses_spent)
                            if uses_limit is not None
                            else None
                        ),
                        "effect": rank["_active_effect"],
                    }
                )
            if passive:
                available_passives.append(
                    {
                        "source": path["name"],
                        "name": rank["name"],
                        "frequency": passive["frequency"],
                        "effect": rank["_passive_effect"],
                    }
                )
    damage_types = {
        "physical": "physiques",
        "elemental": "élémentaires",
        "spiritual": "spirituels",
    }
    for item in equipment:
        if item["item_type"] == "spell":
            effect = " · ".join(
                part
                for part in (
                    (
                        f"{item['damage_dice']} dégâts "
                        f"{damage_types.get(item['damage_type'], item['damage_type'])}"
                        if item["damage_dice"]
                        else ""
                    ),
                    item["effect"],
                )
                if part
            )
            action_name = f"Lancer {item['name']}"
            category = "Sorts"
        elif item["item_type"] == "consumable" and item["equipped"]:
            effect = item["effect"]
            action_name = f"Utiliser {item['name']}"
            category = "Consommables"
        else:
            continue
        available_actions.append(
            {
                "category": category,
                "source": "Inventaire",
                "name": action_name,
                "timing": "Objet",
                "uses": (
                    f"×{item['quantity']}"
                    if item["item_type"] == "consumable"
                    else item["uses"]
                ),
                "effect": effect or "Aucun effet renseigné.",
            }
        )

    stat_labels = {
        "FOR": "Force",
        "DEX": "Dextérité",
        "CON": "Constitution",
        "INT": "Intelligence",
        "SAG": "Sagesse",
        "CHA": "Charisme",
    }
    for item in equipped:
        passive_parts = []
        if item["physical_bonus"]:
            passive_parts.append(f"{item['physical_bonus']:+d} Défense physique")
        if item["elemental_bonus"]:
            passive_parts.append(f"{item['elemental_bonus']:+d} Défense élémentaire")
        if item["spiritual_bonus"]:
            passive_parts.append(f"{item['spiritual_bonus']:+d} Défense spirituelle")
        if item["stat"] and item["stat_bonus"]:
            passive_parts.append(
                f"{item['stat_bonus']:+d} {stat_labels.get(item['stat'], item['stat'])}"
            )
        if item["item_type"] == "tool" and item["effect"]:
            passive_parts.append(item["effect"])
        if passive_parts:
            available_passives.append(
                {
                    "source": "Inventaire",
                    "name": item["name"],
                    "frequency": "Équipé",
                    "effect": " · ".join(passive_parts),
                }
            )
    defenses = {
        "physical": defense(
            effective_scores["constitution"],
            (item["physical_bonus"] for item in equipped),
        )
        + character["species_physical_bonus"]
        + permanent_defense_bonuses["physical"],
        "elemental": defense(
            effective_scores["intelligence"],
            (item["elemental_bonus"] for item in equipped),
        )
        + character["species_elemental_bonus"]
        + permanent_defense_bonuses["elemental"],
        "spiritual": defense(
            effective_scores["wisdom"],
            (item["spiritual_bonus"] for item in equipped),
        )
        + character["species_spiritual_bonus"]
        + permanent_defense_bonuses["spiritual"],
    }
    defense_abilities = {
        "physical": ("Constitution", "constitution", "physical_bonus"),
        "elemental": ("Intelligence", "intelligence", "elemental_bonus"),
        "spiritual": ("Sagesse", "wisdom", "spiritual_bonus"),
    }
    defense_breakdowns = {}
    for defense_name, (
        ability_label,
        ability_field,
        equipment_field,
    ) in defense_abilities.items():
        parts = [
            {
                "label": f"{ability_label}",
                "value": ability_modifier(effective_scores[ability_field]),
            }
        ]
        parts.extend(
            {"label": item["name"], "value": item[equipment_field]}
            for item in equipped
            if item[equipment_field]
        )
        species_bonus = character[f"species_{defense_name}_bonus"]
        if species_bonus:
            parts.append(
                {
                    "label": f"Race · {character['species_name']}",
                    "value": species_bonus,
                }
            )
        if permanent_defense_bonuses[defense_name]:
            parts.append(
                {
                    "label": "Voies débloquées",
                    "value": permanent_defense_bonuses[defense_name],
                }
            )
        defense_breakdowns[defense_name] = parts
    return render_template(
        "characters/detail.html",
        character=character,
        modifiers=modifiers,
        defenses=defenses,
        defense_breakdowns=defense_breakdowns,
        equipment=equipment,
        effective_scores=effective_scores,
        accessory_ability_bonuses=accessory_ability_bonuses,
        paths=paths,
        unlocked_ranks=unlocked_ranks,
        available_path_points=character["level"] - len(unlocked_rows),
        permanent_defense_bonuses=permanent_defense_bonuses,
        available_racial_bonuses=available_racial_bonuses,
        available_actions=available_actions,
        available_passives=available_passives,
    )


@bp.get("/mj")
@gm_required
def gm_dashboard():
    filters = {
        "character_type": request.args.get("type", ""),
        "visibility": request.args.get("visibility", ""),
        "owner_id": request.args.get("owner", ""),
    }
    conditions = []
    parameters = []
    if filters["character_type"] in CHARACTER_TYPES:
        conditions.append("c.character_type = ?")
        parameters.append(filters["character_type"])
    if filters["visibility"] in VISIBILITIES:
        conditions.append("c.visibility = ?")
        parameters.append(filters["visibility"])
    if filters["owner_id"] == "none":
        conditions.append("c.owner_id IS NULL")
    elif filters["owner_id"].isdigit():
        conditions.append("c.owner_id = ?")
        parameters.append(int(filters["owner_id"]))

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    characters = get_db().execute(
        f"""
        SELECT
            c.id, c.name, c.character_type, c.visibility,
            c.current_hp, c.max_hp, c.portrait_filename,
            p.display_name AS owner_name
        FROM character c
        LEFT JOIN player p ON p.id = c.owner_id
        {where_clause}
        ORDER BY c.visibility, c.name COLLATE NOCASE
        """,
        parameters,
    ).fetchall()
    players = get_db().execute(
        "SELECT id, display_name FROM player ORDER BY display_name"
    ).fetchall()
    return render_template(
        "gm/dashboard.html",
        characters=characters,
        players=players,
        filters=filters,
        character_types=CHARACTER_TYPES,
        visibilities=VISIBILITIES,
    )

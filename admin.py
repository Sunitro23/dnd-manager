import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from auth import gm_required, validate_csrf
from database import get_db
from rules import (
    adjusted_current_hp,
    maximum_hp,
    valid_point_buy,
)

bp = Blueprint("admin", __name__, url_prefix="/mj")

CHARACTER_TYPES = ("player", "ally", "npc", "enemy")
VISIBILITIES = ("campaign", "gm")
ABILITY_FIELDS = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)


def text_field(name, *, required=False, maximum=None):
    value = request.form.get(name, "").strip()
    if required and not value:
        raise ValueError(f'Le champ « {name} » est obligatoire.')
    if maximum and len(value) > maximum:
        raise ValueError(f'Le champ « {name} » ne peut pas dépasser {maximum} caractères.')
    return value


def character_for_admin(character_id):
    character = get_db().execute(
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
        """,
        (character_id,),
    ).fetchone()
    if character is None:
        abort(404)
    return character


def resolve_character_owner(database):
    owner_name = text_field("owner_name", maximum=80)
    if not owner_name:
        return None
    owner = database.execute(
        "SELECT id FROM player WHERE display_name = ? COLLATE NOCASE",
        (owner_name,),
    ).fetchone()
    if owner:
        return owner["id"]
    return database.execute(
        "INSERT INTO player (display_name) VALUES (?)",
        (owner_name,),
    ).lastrowid


@bp.route("/personnages/<int:character_id>/modifier", methods=("GET", "POST"))
@gm_required
def character_edit(character_id):
    database = get_db()
    character = character_for_admin(character_id)
    species_rows = database.execute(
        """
        SELECT id, name
        FROM species
        WHERE configured = 1
        ORDER BY name COLLATE NOCASE
        """,
    ).fetchall()
    players = database.execute(
        """
        SELECT id, display_name
        FROM player
        ORDER BY display_name COLLATE NOCASE
        """,
    ).fetchall()

    if request.method == "POST":
        validate_csrf()
        try:
            name = text_field("name", required=True, maximum=80)
            character_type = request.form.get("character_type", "")
            visibility = request.form.get("visibility", "")
            if character_type not in CHARACTER_TYPES:
                raise ValueError("Type de personnage invalide.")
            if visibility not in VISIBILITIES:
                raise ValueError("Visibilité invalide.")

            try:
                level = int(request.form.get("level", ""))
                species_id = int(request.form.get("species_id", ""))
                expected_version = int(
                    request.form.get("version", str(character["version"]))
                )
                scores = {
                    field: int(request.form.get(field, "")) for field in ABILITY_FIELDS
                }
            except ValueError as error:
                raise ValueError(
                    "Le niveau, l'espèce et les caractéristiques doivent être valides."
                ) from error

            if not character["level"] <= level <= 20:
                raise ValueError(
                    "Le niveau ne peut pas diminuer et doit rester inférieur ou égal à 20."
                )
            selected_species = database.execute(
                "SELECT id FROM species WHERE id = ?",
                (species_id,),
            ).fetchone()
            if selected_species is None:
                raise ValueError("L'espèce sélectionnée n'est pas disponible.")
            racial_path_id = (
                character["racial_path_id"]
                if species_id == character["species_id"]
                else None
            )
            racial_path = None
            if racial_path_id:
                racial_path = database.execute(
                    """
                    SELECT * FROM racial_path
                    WHERE id = ? AND species_id = ? AND configured = 1
                    """,
                    (racial_path_id, species_id),
                ).fetchone()
                if racial_path is None:
                    racial_path_id = None
            if not valid_point_buy(scores.values()):
                raise ValueError(
                    "Les caractéristiques doivent rester entre 8 et 15 et utiliser exactement 27 points."
                )

            owner_id = resolve_character_owner(database)
            accessory_constitution_bonus = database.execute(
                """
                SELECT COALESCE(SUM(stat_bonus), 0) FROM equipment
                WHERE character_id = ? AND equipped = 1
                  AND item_type = 'accessory' AND stat = 'CON'
                """,
                (character_id,),
            ).fetchone()[0]
            new_max_hp = maximum_hp(
                character["hit_die"],
                level,
                scores["constitution"]
                + character["class_constitution_bonus"]
                + (racial_path["constitution_bonus"] if racial_path else 0)
                + accessory_constitution_bonus,
            )
            new_current_hp = adjusted_current_hp(
                character["current_hp"], character["max_hp"], new_max_hp
            )

            values = {
                "id": character_id,
                "version": expected_version,
                "name": name,
                "owner_id": owner_id,
                "species_id": species_id,
                "racial_path_id": racial_path_id,
                "character_type": character_type,
                "visibility": visibility,
                "level": level,
                "current_hp": new_current_hp,
                "max_hp": new_max_hp,
                **scores,
            }
            assignments = ", ".join(f"{field} = :{field}" for field in scores)
            cursor = database.execute(
                f"""
                UPDATE character
                SET name = :name,
                    owner_id = :owner_id,
                    species_id = :species_id,
                    racial_path_id = :racial_path_id,
                    character_type = :character_type,
                    visibility = :visibility,
                    level = :level,
                    current_hp = :current_hp,
                    max_hp = :max_hp,
                    {assignments},
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND version = :version
                """,
                values,
            )
            if cursor.rowcount == 0:
                database.rollback()
                abort(409, "La fiche a été modifiée simultanément. Recharge la page.")
            if species_id != character["species_id"]:
                database.execute(
                    """
                    DELETE FROM character_rank
                    WHERE character_id = ? AND path_type = 'racial'
                    """,
                    (character_id,),
                )
            database.commit()
        except (ValueError, sqlite3.IntegrityError) as error:
            database.rollback()
            message = (
                "Ce nom de propriétaire existe déjà."
                if isinstance(error, sqlite3.IntegrityError)
                else str(error)
            )
            flash(message, "error")
        else:
            flash("Personnage mis à jour.", "success")
            return redirect(url_for("main.character_detail", character_id=character_id))

        character = character_for_admin(character_id)

    return render_template(
        "admin/character_form.html",
        character=character,
        species=species_rows,
        players=players,
        character_types=CHARACTER_TYPES,
        visibilities=VISIBILITIES,
        abilities=ABILITY_FIELDS,
    )


@bp.post("/personnages/<int:character_id>/dupliquer")
@gm_required
def character_duplicate(character_id):
    validate_csrf()
    database = get_db()
    source = character_for_admin(character_id)
    copy_name = f"{source['name'][:68]} — copie"

    cursor = database.execute(
        """
        INSERT INTO character
            (
                campaign_id, owner_id, class_id, species_id,
                class_path_id, racial_path_id, name,
                character_type, visibility, level, description, personal_info,
                strength, dexterity, constitution, intelligence, wisdom,
                charisma, current_hp, max_hp
            )
        SELECT
            campaign_id, NULL, class_id, species_id,
            class_path_id, racial_path_id, ?,
            character_type, visibility, level, description, personal_info,
            strength, dexterity, constitution, intelligence, wisdom,
            charisma, current_hp, max_hp
        FROM character
        WHERE id = ?
        """,
        (copy_name, character_id),
    )
    copy_id = cursor.lastrowid
    database.execute(
        """
        INSERT INTO character_rank (character_id, path_type, path_id, rank)
        SELECT ?, path_type, path_id, rank
        FROM character_rank
        WHERE character_id = ?
        """,
        (copy_id, character_id),
    )
    database.execute(
        """
        INSERT INTO equipment
            (
                character_id, name, item_type, quantity, equipped,
                physical_bonus, elemental_bonus, spiritual_bonus, notes
            )
        SELECT
            ?, name, item_type, quantity, equipped,
            physical_bonus, elemental_bonus, spiritual_bonus, notes
        FROM equipment
        WHERE character_id = ?
        """,
        (copy_id, character_id),
    )
    database.commit()
    flash("Personnage dupliqué sans propriétaire.", "success")
    return redirect(url_for("main.character_detail", character_id=copy_id))

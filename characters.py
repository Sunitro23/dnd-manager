import json
import re
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    Response,
    send_from_directory,
    url_for,
)

from access import accessible_character
from auth import validate_csrf
from database import get_db
from rules import adjusted_current_hp, maximum_hp

bp = Blueprint("characters", __name__, url_prefix="/personnages")

ITEM_TYPES = (
    "weapon",
    "armor",
    "shield",
    "accessory",
    "tool",
    "consumable",
    "spell",
    "quest",
    "other",
)
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
)
EQUIPMENT_SLOTS = {
    "weapon": ("right_hand", "left_hand"),
    "shield": ("right_hand", "left_hand"),
    "tool": ("right_hand", "left_hand"),
    "armor": ("armor",),
    "accessory": ("ring_1", "ring_2", "ring_3", "ring_4"),
}
ITEM_ICON_ROOT = Path(__file__).with_name("assets") / "item-icons"
INTERFACE_ASSET_ROOT = Path(__file__).with_name("static") / "icons" / "interface"
ITEM_ICON_DIRECTORIES = {
    "weapon": ("01_weapons", "06_arrows"),
    "shield": ("02_shields",),
    "armor": ("03_armor",),
    "accessory": ("05_rings",),
    "spell": ("04_spells",),
    "tool": ("07_catalysts",),
    "consumable": ("00_items",),
    "quest": ("00_items",),
    "other": ("00_items",),
}
def limited_action_uses(uses):
    match = re.match(r"^(\d+)\s+(?:fois|charges)\b", uses, re.IGNORECASE)
    return int(match.group(1)) if match else None


def valid_item_icon_path(value):
    if not value:
        return ""
    root = ITEM_ICON_ROOT.resolve()
    candidate = (root / value).resolve()
    if (
        root not in candidate.parents
        or not candidate.is_file()
        or candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
    ):
        raise ValueError("Icône d’objet invalide.")
    return candidate.relative_to(root).as_posix()


def optional_text(name, maximum):
    value = request.form.get(name, "").strip()
    if len(value) > maximum:
        raise ValueError(f'Le champ « {name} » ne peut pas dépasser {maximum} caractères.')
    return value


def required_text(name, maximum):
    value = optional_text(name, maximum)
    if not value:
        raise ValueError(f'Le champ « {name} » est obligatoire.')
    return value


def integer_field(name, *, minimum=None):
    try:
        value = int(request.form.get(name, ""))
    except ValueError as error:
        raise ValueError(f'Le champ « {name} » doit être un nombre entier.') from error
    if minimum is not None and value < minimum:
        raise ValueError(f'Le champ « {name} » doit être supérieur ou égal à {minimum}.')
    return value


def asynchronous_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def saved_response(message, **values):
    if asynchronous_request():
        return jsonify(ok=True, message=message, **values)
    flash(message, "success")
    return redirect(url_for("main.character_detail", character_id=values["character_id"]))


@bp.post("/<int:character_id>/bonus-racial")
def choose_racial_bonus(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    try:
        path_id = int(request.form.get("racial_path_id", ""))
    except ValueError:
        abort(400, "Bonus racial invalide.")

    database = get_db()
    path = database.execute(
        """
        SELECT rp.*, cc.hit_die, cc.constitution_bonus AS class_constitution_bonus
        FROM racial_path rp
        JOIN character_class cc ON cc.id = ?
        WHERE rp.id = ? AND rp.species_id = ? AND rp.configured = 1
        """,
        (character["class_id"], path_id, character["species_id"]),
    ).fetchone()
    if path is None:
        abort(400, "Ce bonus ne correspond pas à la race du personnage.")

    rank_one = database.execute(
        """
        SELECT 1 FROM character_rank
        WHERE character_id = ? AND path_type = 'racial'
          AND path_id = ? AND rank = 1
        """,
        (character_id, path_id),
    ).fetchone()
    if rank_one is None:
        if asynchronous_request():
            return jsonify(ok=False, message="Débloque d’abord le rang 1."), 400
        flash("Débloque d’abord le rang 1 de cette voie.", "error")
        return redirect(url_for("main.character_detail", character_id=character_id))

    new_max_hp = maximum_hp(
        path["hit_die"],
        character["level"],
        character["constitution"]
        + path["class_constitution_bonus"]
        + path["constitution_bonus"]
        + database.execute(
            """
            SELECT COALESCE(SUM(stat_bonus), 0) FROM equipment
            WHERE character_id = ? AND equipped = 1
              AND item_type = 'accessory' AND stat = 'CON'
            """,
            (character_id,),
        ).fetchone()[0],
    )
    new_current_hp = adjusted_current_hp(
        character["current_hp"], character["max_hp"], new_max_hp
    )
    database.execute(
        """
        UPDATE character
        SET racial_path_id = ?, current_hp = ?, max_hp = ?,
            version = version + 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (path_id, new_current_hp, new_max_hp, character_id),
    )
    database.commit()
    return saved_response(
        f"Bonus de {path['name']} appliqué.",
        character_id=character_id,
        current_hp=new_current_hp,
        max_hp=new_max_hp,
        refresh_sheet=True,
    )


@bp.post("/<int:character_id>/rangs")
def unlock_rank(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    path_type = request.form.get("path_type", "")
    if path_type not in {"class", "racial"}:
        abort(400, "Type de voie invalide.")

    try:
        path_id = int(request.form.get("path_id", ""))
    except ValueError:
        abort(400, "Voie invalide.")

    database = get_db()
    table = "class_path" if path_type == "class" else "racial_path"
    owner_column = "class_id" if path_type == "class" else "species_id"
    character_owner_id = (
        character["class_id"] if path_type == "class" else character["species_id"]
    )
    path = database.execute(
        f"""
        SELECT id FROM {table}
        WHERE id = ? AND {owner_column} = ? AND configured = 1
        """,
        (path_id, character_owner_id),
    ).fetchone()
    if path is None:
        abort(400, "Cette voie n'est pas proposée à ce personnage.")
    spent_points = database.execute(
        "SELECT COUNT(*) FROM character_rank WHERE character_id = ?",
        (character_id,),
    ).fetchone()[0]
    if spent_points >= character["level"]:
        if asynchronous_request():
            return jsonify(ok=False, message="Aucun point de voie disponible."), 400
        flash("Aucun point de voie disponible.", "error")
        return redirect(url_for("main.character_detail", character_id=character_id))

    next_rank = (
        database.execute(
            """
            SELECT COALESCE(MAX(rank), 0) + 1
            FROM character_rank
            WHERE character_id = ? AND path_type = ? AND path_id = ?
            """,
            (character_id, path_type, path_id),
        ).fetchone()[0]
    )
    if next_rank > 5:
        if asynchronous_request():
            return jsonify(ok=False, message="Cette voie est déjà complète."), 400
        flash("Cette voie est déjà complète.", "error")
        return redirect(url_for("main.character_detail", character_id=character_id))

    database.execute(
        """
        INSERT INTO character_rank (character_id, path_type, path_id, rank)
        VALUES (?, ?, ?, ?)
        """,
        (character_id, path_type, path_id, next_rank),
    )
    database.commit()
    return saved_response(
        f"Rang {next_rank} débloqué.",
        character_id=character_id,
        refresh_sheet=True,
    )


@bp.post("/<int:character_id>/niveau")
def level_up(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    if character["level"] >= 20:
        if asynchronous_request():
            return jsonify(ok=False, message="Le niveau maximum est déjà atteint."), 400
        flash("Le niveau maximum est déjà atteint.", "error")
        return redirect(url_for("main.character_detail", character_id=character_id))

    database = get_db()
    progression = database.execute(
        """
        SELECT cc.hit_die,
               cc.constitution_bonus AS class_constitution_bonus,
               COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus,
               COALESCE((
                   SELECT SUM(e.stat_bonus) FROM equipment e
                   WHERE e.character_id = c.id AND e.equipped = 1
                     AND e.item_type = 'accessory' AND e.stat = 'CON'
               ), 0) AS accessory_constitution_bonus
        FROM character c
        JOIN character_class cc ON cc.id = c.class_id
        LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
        WHERE c.id = ?
        """,
        (character_id,),
    ).fetchone()
    new_level = character["level"] + 1
    new_max_hp = maximum_hp(
        progression["hit_die"],
        new_level,
        character["constitution"]
        + progression["class_constitution_bonus"]
        + progression["racial_constitution_bonus"]
        + progression["accessory_constitution_bonus"],
    )
    new_current_hp = adjusted_current_hp(
        character["current_hp"], character["max_hp"], new_max_hp
    )
    cursor = database.execute(
        """
        UPDATE character
        SET level = ?, current_hp = ?, max_hp = ?,
            version = version + 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND version = ?
        """,
        (
            new_level,
            new_current_hp,
            new_max_hp,
            character_id,
            character["version"],
        ),
    )
    if cursor.rowcount == 0:
        database.rollback()
        abort(409, "La fiche a été modifiée simultanément. Recharge la page.")
    database.commit()
    return saved_response(
        f"Niveau {new_level} atteint : 1 point de voie gagné.",
        character_id=character_id,
        current_hp=new_current_hp,
        max_hp=new_max_hp,
        refresh_sheet=True,
    )


@bp.post("/<int:character_id>/pv")
def update_hp(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    action = request.form.get("action", "")
    old_hp = character["current_hp"]

    try:
        if action in {"maximum", "estus", "rest"}:
            new_hp = character["max_hp"]
            if action == "estus" and not character["estus_available"]:
                raise ValueError("L’Estus a déjà été utilisé depuis le dernier repos.")
        else:
            amount = integer_field("amount", minimum=1)
            if action == "damage":
                damage_type = request.form.get("damage_type", "physical")
                if damage_type not in {"physical", "elemental", "spiritual"}:
                    raise ValueError("Type de dégâts invalide.")
                try:
                    defense_value = int(
                        request.form.get(f"{damage_type}_defense", "0")
                    )
                except ValueError as error:
                    raise ValueError("Valeur de défense invalide.") from error
                damage_received = max(0, amount - defense_value)
                new_hp = max(0, old_hp - damage_received)
            elif action == "heal":
                new_hp = min(character["max_hp"], old_hp + amount)
            elif action == "set":
                new_hp = min(character["max_hp"], amount)
            else:
                raise ValueError("Action de PV inconnue.")
    except ValueError as error:
        if asynchronous_request():
            return jsonify(ok=False, message=str(error)), 400
        flash(str(error), "error")
        return redirect(url_for("main.character_detail", character_id=character_id))

    database = get_db()
    estus_available = character["estus_available"]
    if action == "estus":
        estus_available = 0
    elif action == "rest":
        estus_available = 1
        database.execute(
            "DELETE FROM character_action_use WHERE character_id = ?",
            (character_id,),
        )
    cursor = database.execute(
        """
        UPDATE character SET current_hp = ?, estus_available = ?,
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND version = ?
        """,
        (new_hp, estus_available, character_id, character["version"]),
    )
    if cursor.rowcount == 0:
        database.rollback()
        abort(409, "La fiche a été modifiée simultanément. Recharge la page.")

    database.commit()
    return saved_response(
        f"PV mis à jour : {old_hp} → {new_hp}.",
        character_id=character_id,
        current_hp=new_hp,
        max_hp=character["max_hp"],
        estus_available=estus_available,
        refresh_sheet=action == "rest",
    )


@bp.post("/<int:character_id>/competences/utiliser")
def use_action(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    path_type = request.form.get("path_type", "")
    if path_type not in {"class", "racial"}:
        abort(400, "Type de voie invalide.")
    try:
        path_id = int(request.form.get("path_id", ""))
        rank_number = int(request.form.get("rank", ""))
    except ValueError:
        abort(400, "Compétence invalide.")
    if rank_number not in range(1, 6):
        abort(400, "Rang invalide.")

    table = "class_path" if path_type == "class" else "racial_path"
    owner_field = "class_id" if path_type == "class" else "species_id"
    owner_id = (
        character["class_id"] if path_type == "class" else character["species_id"]
    )
    database = get_db()
    path = database.execute(
        f"""
        SELECT ranks_json FROM {table}
        WHERE id = ? AND {owner_field} = ? AND configured = 1
        """,
        (path_id, owner_id),
    ).fetchone()
    unlocked = database.execute(
        """
        SELECT 1 FROM character_rank
        WHERE character_id = ? AND path_type = ? AND path_id = ? AND rank = ?
        """,
        (character_id, path_type, path_id, rank_number),
    ).fetchone()
    if path is None or unlocked is None:
        abort(400, "Cette compétence n’est pas débloquée.")

    rank = json.loads(path["ranks_json"])[rank_number - 1]
    active = rank.get("active")
    limit = limited_action_uses(active["uses"]) if active else None
    if limit is None:
        abort(400, "Cette compétence n’utilise pas de compteur de repos.")
    spent = database.execute(
        """
        SELECT uses_spent FROM character_action_use
        WHERE character_id = ? AND path_type = ? AND path_id = ? AND rank = ?
        """,
        (character_id, path_type, path_id, rank_number),
    ).fetchone()
    spent_count = spent["uses_spent"] if spent else 0
    if spent_count >= limit:
        return jsonify(ok=False, message="Aucune utilisation restante."), 400

    database.execute(
        """
        INSERT INTO character_action_use
            (character_id, path_type, path_id, rank, uses_spent)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(character_id, path_type, path_id, rank)
        DO UPDATE SET uses_spent = uses_spent + 1
        """,
        (character_id, path_type, path_id, rank_number),
    )
    database.commit()
    return saved_response(
        f"{rank['name']} utilisée.",
        character_id=character_id,
        action_key=f"{path_type}:{path_id}:{rank_number}",
        remaining=limit - spent_count - 1,
    )


@bp.post("/<int:character_id>/textes")
def update_texts(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    try:
        description = optional_text("description", 4000)
        personal_info = optional_text("personal_info", 4000)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("main.character_detail", character_id=character_id))

    database = get_db()
    cursor = database.execute(
        """
        UPDATE character
        SET description = ?,
            personal_info = ?,
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND version = ?
        """,
        (description, personal_info, character_id, character["version"]),
    )
    if cursor.rowcount == 0:
        database.rollback()
        abort(409, "La fiche a été modifiée simultanément. Recharge la page.")

    database.commit()
    return saved_response("Description mise à jour.", character_id=character_id)


@bp.get("/<int:character_id>/portrait")
def portrait(character_id):
    character = accessible_character(character_id)
    if not character["portrait_filename"]:
        return Response(status=204)
    portrait_path = (
        Path(current_app.config["PORTRAIT_PATH"]) / character["portrait_filename"]
    )
    if not portrait_path.is_file():
        return Response(status=204)
    return send_from_directory(
        current_app.config["PORTRAIT_PATH"],
        character["portrait_filename"],
        max_age=86400,
    )


@bp.post("/<int:character_id>/portrait")
def update_portrait(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    uploaded = request.files.get("portrait")
    if uploaded is None:
        return jsonify(ok=False, message="Choisis une image."), 400

    content = uploaded.read()
    suffix = next(
        (extension for signature, extension in IMAGE_SIGNATURES if content.startswith(signature)),
        ".webp"
        if len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP"
        else None,
    )
    if not content or suffix is None:
        return jsonify(
            ok=False,
            message="Utilise une image PNG, JPEG ou WebP.",
        ), 400

    filename = f"{uuid4().hex}{suffix}"
    portrait_directory = Path(current_app.config["PORTRAIT_PATH"])
    (portrait_directory / filename).write_bytes(content)
    database = get_db()
    database.execute(
        """
        UPDATE character
        SET portrait_filename = ?, version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (filename, character_id),
    )
    database.commit()

    if character["portrait_filename"]:
        (portrait_directory / character["portrait_filename"]).unlink(missing_ok=True)

    image_url = url_for("characters.portrait", character_id=character_id)
    if asynchronous_request():
        return jsonify(ok=True, message="Portrait enregistré.", image_url=image_url)
    return redirect(url_for("main.character_detail", character_id=character_id))


def equipment_values():
    item_type = request.form.get("item_type", "")
    if item_type not in ITEM_TYPES:
        raise ValueError("Type d'objet invalide.")
    values = {
        "name": required_text("name", 100),
        "item_type": item_type,
        "quantity": (
            integer_field("quantity", minimum=1)
            if item_type in {"consumable", "quest"}
            else 1
        ),
        "equipped": 1 if request.form.get("equipped") == "1" else 0,
        "physical_bonus": integer_field("physical_bonus"),
        "elemental_bonus": integer_field("elemental_bonus"),
        "spiritual_bonus": integer_field("spiritual_bonus"),
        "damage_dice": optional_text("damage_dice", 50),
        "damage_type": optional_text("damage_type", 50),
        "uses": optional_text("uses", 80),
        "stat": optional_text("stat", 30),
        "stat_bonus": int(request.form.get("stat_bonus", "0")),
        "icon_path": valid_item_icon_path(optional_text("icon_path", 200)),
        "effect": optional_text("effect", 300),
        "notes": optional_text("notes", 2000),
    }
    if item_type not in {"armor", "shield"}:
        for field in ("physical_bonus", "elemental_bonus", "spiritual_bonus"):
            values[field] = 0
    if item_type not in {"weapon", "spell"}:
        values["damage_dice"] = ""
        values["damage_type"] = ""
    if item_type != "spell":
        values["uses"] = ""
    if item_type != "accessory":
        values["stat"] = ""
        values["stat_bonus"] = 0
    return values


def recalculate_hp_from_accessories(database, character_id):
    character = database.execute(
        """
        SELECT c.level, c.constitution, c.current_hp, c.max_hp,
               cc.hit_die,
               cc.constitution_bonus AS class_constitution_bonus,
               COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus,
               COALESCE((
                   SELECT SUM(e.stat_bonus)
                   FROM equipment e
                   WHERE e.character_id = c.id
                     AND e.equipped = 1
                     AND e.item_type = 'accessory'
                     AND e.stat = 'CON'
               ), 0) AS accessory_constitution_bonus
        FROM character c
        JOIN character_class cc ON cc.id = c.class_id
        LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
        WHERE c.id = ?
        """,
        (character_id,),
    ).fetchone()
    new_max_hp = maximum_hp(
        character["hit_die"],
        character["level"],
        character["constitution"]
        + character["class_constitution_bonus"]
        + character["racial_constitution_bonus"]
        + character["accessory_constitution_bonus"],
    )
    new_current_hp = adjusted_current_hp(
        character["current_hp"], character["max_hp"], new_max_hp
    )
    database.execute(
        """
        UPDATE character
        SET current_hp = ?, max_hp = ?,
            version = version + 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_current_hp, new_max_hp, character_id),
    )


def first_available_slot(database, character_id, item_type, equipment_id=None):
    slots = EQUIPMENT_SLOTS.get(item_type, ())
    if not slots:
        return None
    occupied = {
        row["slot"]
        for row in database.execute(
            """
            SELECT slot FROM equipment
            WHERE character_id = ? AND equipped = 1 AND slot != ''
              AND (? IS NULL OR id != ?)
            """,
            (character_id, equipment_id, equipment_id),
        ).fetchall()
    }
    return next((slot for slot in slots if slot not in occupied), None)


def normalize_equipment_slot(database, character_id, equipment_id, item_type, equipped):
    if not equipped:
        database.execute(
            "UPDATE equipment SET equipped = 0, slot = '' WHERE id = ?",
            (equipment_id,),
        )
        return None
    current = database.execute(
        "SELECT slot FROM equipment WHERE id = ?", (equipment_id,)
    ).fetchone()["slot"]
    allowed_slots = EQUIPMENT_SLOTS.get(item_type, ())
    if current in allowed_slots:
        return current
    slot = first_available_slot(database, character_id, item_type, equipment_id)
    database.execute(
        "UPDATE equipment SET equipped = ?, slot = ? WHERE id = ?",
        (1 if slot else 0, slot or "", equipment_id),
    )
    return slot


@bp.get("/<int:character_id>/equipement")
def equipment_index(character_id):
    character = accessible_character(character_id)
    equipment = get_db().execute(
        """
        SELECT * FROM equipment
        WHERE character_id = ?
        ORDER BY equipped DESC, name COLLATE NOCASE
        """,
        (character_id,),
    ).fetchall()
    return render_template(
        "characters/equipment.html",
        character=character,
        equipment=equipment,
        item_types=ITEM_TYPES,
    )


@bp.route("/<int:character_id>/equipement/nouveau", methods=("GET", "POST"))
def equipment_create(character_id):
    accessible_character(character_id)
    if request.method == "POST":
        validate_csrf()
        try:
            values = equipment_values()
            values["character_id"] = character_id
            database = get_db()
            cursor = database.execute(
                """
                INSERT INTO equipment
                    (
                        character_id, name, item_type, quantity, equipped,
                        physical_bonus, elemental_bonus, spiritual_bonus,
                        damage_dice, damage_type, uses, stat, stat_bonus,
                        icon_path, effect, notes
                    )
                VALUES
                    (
                        :character_id, :name, :item_type, :quantity, :equipped,
                        :physical_bonus, :elemental_bonus, :spiritual_bonus,
                        :damage_dice, :damage_type, :uses, :stat, :stat_bonus,
                        :icon_path, :effect, :notes
                    )
                """,
                values,
            )
            if values["equipped"]:
                slot = normalize_equipment_slot(
                    database,
                    character_id,
                    cursor.lastrowid,
                    values["item_type"],
                    True,
                )
                if slot is None:
                    raise ValueError("Aucun emplacement compatible n’est disponible.")
            recalculate_hp_from_accessories(database, character_id)
            database.commit()
        except ValueError as error:
            get_db().rollback()
            flash(str(error), "error")
        else:
            if not asynchronous_request() and request.form.get("return_to") == "equipment":
                flash("Objet ajouté.", "success")
                return redirect(
                    url_for("characters.equipment_index", character_id=character_id)
                )
            return saved_response(
                "Objet ajouté.", character_id=character_id, refresh_sheet=True
            )

    return render_template(
        "characters/equipment_form.html",
        character_id=character_id,
        equipment=None,
        item_types=ITEM_TYPES,
    )


@bp.post("/<int:character_id>/equipement/rapide")
def equipment_quick_create(character_id):
    validate_csrf()
    accessible_character(character_id)
    item_type = request.form.get("item_type", "")
    if item_type not in ITEM_TYPES:
        abort(400, "Type d’objet invalide.")
    labels = {
        "weapon": "Nouvelle arme",
        "armor": "Nouvelle armure",
        "shield": "Nouveau bouclier",
        "accessory": "Nouvel anneau",
        "tool": "Nouvel outil",
        "consumable": "Nouveau consommable",
        "spell": "Nouveau sort",
        "quest": "Nouvel objet clé",
        "other": "Nouvel objet",
    }
    database = get_db()
    equipment_id = database.execute(
        """
        INSERT INTO equipment (character_id, name, item_type)
        VALUES (?, ?, ?)
        """,
        (character_id, labels[item_type], item_type),
    ).lastrowid
    database.commit()
    return saved_response(
        "Objet créé. Renseigne maintenant sa fiche.",
        character_id=character_id,
        selected_item_id=equipment_id,
        refresh_sheet=True,
    )


def accessible_equipment(character_id, equipment_id):
    accessible_character(character_id)
    equipment = get_db().execute(
        "SELECT * FROM equipment WHERE id = ? AND character_id = ?",
        (equipment_id, character_id),
    ).fetchone()
    if equipment is None:
        abort(404)
    return equipment


@bp.route(
    "/<int:character_id>/equipement/<int:equipment_id>/modifier",
    methods=("GET", "POST"),
)
def equipment_edit(character_id, equipment_id):
    equipment = accessible_equipment(character_id, equipment_id)
    if request.method == "POST":
        validate_csrf()
        try:
            values = equipment_values()
            values.update({"id": equipment_id, "character_id": character_id})
            database = get_db()
            database.execute(
                """
                UPDATE equipment
                SET name = :name,
                    item_type = :item_type,
                    quantity = :quantity,
                    equipped = :equipped,
                    physical_bonus = :physical_bonus,
                    elemental_bonus = :elemental_bonus,
                    spiritual_bonus = :spiritual_bonus,
                    damage_dice = :damage_dice,
                    damage_type = :damage_type,
                    uses = :uses,
                    stat = :stat,
                    stat_bonus = :stat_bonus,
                    icon_path = :icon_path,
                    effect = :effect,
                    notes = :notes
                WHERE id = :id AND character_id = :character_id
                """,
                values,
            )
            if values["equipped"]:
                slot = normalize_equipment_slot(
                    database,
                    character_id,
                    equipment_id,
                    values["item_type"],
                    True,
                )
                if slot is None:
                    raise ValueError("Aucun emplacement compatible n’est disponible.")
            else:
                normalize_equipment_slot(
                    database, character_id, equipment_id, values["item_type"], False
                )
            recalculate_hp_from_accessories(database, character_id)
            database.commit()
        except ValueError as error:
            get_db().rollback()
            flash(str(error), "error")
        else:
            if not asynchronous_request() and request.args.get("return_to") == "equipment":
                flash("Objet mis à jour.", "success")
                return redirect(
                    url_for("characters.equipment_index", character_id=character_id)
                )
            return saved_response(
                "Objet mis à jour.",
                character_id=character_id,
                selected_item_id=equipment_id,
                refresh_sheet=True,
            )

        equipment = accessible_equipment(character_id, equipment_id)

    return render_template(
        "characters/equipment_form.html",
        character_id=character_id,
        equipment=equipment,
        item_types=ITEM_TYPES,
    )


@bp.post("/<int:character_id>/equipement/<int:equipment_id>/supprimer")
def equipment_delete(character_id, equipment_id):
    validate_csrf()
    accessible_equipment(character_id, equipment_id)
    database = get_db()
    database.execute(
        "DELETE FROM equipment WHERE id = ? AND character_id = ?",
        (equipment_id, character_id),
    )
    recalculate_hp_from_accessories(database, character_id)
    database.commit()
    return saved_response(
        "Objet supprimé.", character_id=character_id, refresh_sheet=True
    )


@bp.post("/<int:character_id>/equipement/<int:equipment_id>/equiper")
def equipment_toggle(character_id, equipment_id):
    validate_csrf()
    equipment = accessible_equipment(character_id, equipment_id)
    database = get_db()
    equipped = not equipment["equipped"]
    slot = normalize_equipment_slot(
        database,
        character_id,
        equipment_id,
        equipment["item_type"],
        equipped,
    )
    if equipped and slot is None:
        if equipment["item_type"] not in EQUIPMENT_SLOTS:
            abort(400, "Ce type d’objet ne peut pas être équipé.")
        abort(400, "Tous les emplacements compatibles sont déjà occupés.")
    recalculate_hp_from_accessories(database, character_id)
    database.commit()
    return saved_response(
        "Objet équipé." if equipped else "Objet retiré.",
        character_id=character_id,
        selected_item_id=equipment_id,
        refresh_sheet=True,
    )


@bp.post("/<int:character_id>/equipement/<int:equipment_id>/utiliser")
def equipment_use(character_id, equipment_id):
    validate_csrf()
    equipment = accessible_equipment(character_id, equipment_id)
    if equipment["item_type"] != "consumable":
        abort(400, "Seul un consommable peut être utilisé.")
    database = get_db()
    if equipment["quantity"] > 1:
        database.execute(
            "UPDATE equipment SET quantity = quantity - 1 WHERE id = ?",
            (equipment_id,),
        )
    else:
        database.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))
    database.commit()
    return saved_response(
        f"{equipment['name']} utilisé.",
        character_id=character_id,
        refresh_sheet=True,
    )


@bp.get("/icones/fichier/<path:icon_path>")
def item_icon(icon_path):
    try:
        valid_path = valid_item_icon_path(icon_path)
    except ValueError:
        abort(404)
    return send_from_directory(ITEM_ICON_ROOT, valid_path, max_age=86400)


@bp.get("/interface/<path:asset_path>")
def interface_asset(asset_path):
    if "/" in asset_path or "\\" in asset_path:
        abort(404)
    root = INTERFACE_ASSET_ROOT.resolve()
    candidate = (root / asset_path).resolve()
    if (
        root not in candidate.parents
        or not candidate.is_file()
        or candidate.suffix.lower() != ".png"
    ):
        abort(404)
    return send_from_directory(root, candidate.relative_to(root), max_age=86400)


@bp.get("/bibliotheque-icones/<item_type>")
def item_icon_library(item_type):
    directories = ITEM_ICON_DIRECTORIES.get(item_type)
    if directories is None:
        abort(404)
    try:
        page = max(0, int(request.args.get("page", "0")))
    except ValueError:
        abort(400, "Page invalide.")
    per_page = 200
    icon_paths = sorted(
        path.relative_to(ITEM_ICON_ROOT).as_posix()
        for directory in directories
        for path in (ITEM_ICON_ROOT / directory).iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    start = page * per_page
    selected = icon_paths[start : start + per_page]
    return jsonify(
        ok=True,
        icons=[
            {
                "path": path,
                "url": url_for("characters.item_icon", icon_path=path),
            }
            for path in selected
        ],
        next_page=page + 1 if start + per_page < len(icon_paths) else None,
    )


@bp.post("/<int:character_id>/equipement/<int:equipment_id>/dupliquer")
def equipment_duplicate(character_id, equipment_id):
    validate_csrf()
    equipment = accessible_equipment(character_id, equipment_id)
    database = get_db()
    database.execute(
        """
        INSERT INTO equipment (
            character_id, name, item_type, quantity, equipped,
            physical_bonus, elemental_bonus, spiritual_bonus,
            damage_dice, damage_type, uses, stat, stat_bonus, icon_path, effect, notes
        )
        VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            character_id,
            f"{equipment['name']} — copie",
            equipment["item_type"],
            equipment["quantity"],
            equipment["physical_bonus"],
            equipment["elemental_bonus"],
            equipment["spiritual_bonus"],
            equipment["damage_dice"],
            equipment["damage_type"],
            equipment["uses"],
            equipment["stat"],
            equipment["stat_bonus"],
            equipment["icon_path"],
            equipment["effect"],
            equipment["notes"],
        ),
    )
    database.commit()
    return saved_response(
        "Objet dupliqué.", character_id=character_id, refresh_sheet=True
    )

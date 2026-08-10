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

from dnd_manager.characters.sheet.access import accessible_character
from dnd_manager.authentication.http import is_gm, validate_csrf
from dnd_manager.infrastructure.database import get_db
from dnd_manager.infrastructure.dice import RandomDiceRoller
from dnd_manager.characters.progression import (
    ActionCommand,
    ChooseRacialBonus,
    RaiseLevel,
    RacialBonusCommand,
    RankCommand,
    UnlockRank,
    UseAction,
)
from dnd_manager.characters.progression.sqlite_repository import SqliteProgressionRepository
from dnd_manager.characters.inventory.item_form import (
    equipment_values,
)
from dnd_manager.characters.inventory.sqlite_repository import (
    equipment_for_character,
    find_equipment,
)
from dnd_manager.characters.health import ChangeHealth, HealthCommand
from dnd_manager.characters.health.sqlite_repository import SqliteHealthRepository
from dnd_manager.characters.inventory import (
    ConsumeCommand,
    ConsumeItem,
    DeleteCommand,
    DeleteItem,
    DuplicateCommand,
    DuplicateItem,
    QuickCreateCommand,
    QuickCreateItem,
    SaveItem,
    SaveItemCommand,
    ToggleCommand,
    ToggleItem,
)
from dnd_manager.characters.inventory.sqlite_repository import SqliteInventoryRepository
from dnd_manager.shared.errors import (
    ApplicationError,
    ConcurrentUpdate,
    InvalidRequest,
    RepositoryUnavailable,
    ResourceNotFound,
)
from dnd_manager.characters.inventory.icons import icon_page, interface_asset_path, page_number
from dnd_manager.shared.catalog import ITEM_TYPES

bp = Blueprint("characters", __name__, url_prefix="/personnages")

IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
)
PROJECT_ROOT = Path(__file__).parents[2]
ITEM_ICON_ROOT = PROJECT_ROOT / "assets" / "item-icons"
INTERFACE_ASSET_ROOT = PROJECT_ROOT / "static" / "icons" / "interface"
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
ITEM_ICON_CATEGORIES = {
    "items": ("Objets", ("00_items",)),
    "weapons": ("Armes", ("01_weapons",)),
    "shields": ("Boucliers", ("02_shields",)),
    "armor": ("Armures", ("03_armor",)),
    "spells": ("Sorts", ("04_spells",)),
    "rings": ("Anneaux", ("05_rings",)),
    "arrows": ("Projectiles", ("06_arrows",)),
    "tools": ("Catalyseurs", ("07_catalysts",)),
}
UPDATE_PORTRAIT_SQL = """
UPDATE character SET portrait_filename = ?, version = version + 1,
    updated_at = CURRENT_TIMESTAMP WHERE id = ?
"""


def valid_item_icon_path(value):
    if not value:
        return ""
    return checked_icon_path(value)


def checked_icon_path(value):
    root, candidate = resolved_icon(value)
    if not valid_icon_candidate(root, candidate):
        raise ValueError("Icône d’objet invalide.")
    return candidate.relative_to(root).as_posix()


def resolved_icon(value):
    root = ITEM_ICON_ROOT.resolve()
    return root, (root / value).resolve()


def valid_icon_candidate(root, candidate):
    extensions = {".png", ".jpg", ".jpeg", ".webp"}
    return root in candidate.parents and candidate.is_file() and candidate.suffix.lower() in extensions


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
    value = parsed_integer(name)
    if minimum is not None and value < minimum:
        raise ValueError(f'Le champ « {name} » doit être supérieur ou égal à {minimum}.')
    return value


def parsed_integer(name):
    try:
        return int(request.form.get(name, ""))
    except ValueError as error:
        raise ValueError(f'Le champ « {name} » doit être un nombre entier.') from error


def asynchronous_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def saved_response(message, **values):
    if asynchronous_request():
        return jsonify(ok=True, message=message, **values)
    flash(message, "success")
    return redirect(url_for("main.character_detail", character_id=values["character_id"]))


def form_integer(name, message):
    try:
        return int(request.form.get(name, ""))
    except ValueError:
        abort(400, message)


def choose_bonus_response(character_id, command):
    try:
        result = racial_bonus_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return racial_bonus_success(result)


def racial_bonus_success(result):
    return saved_response(f"Bonus de {result.path_name} appliqué.",
                          character_id=result.character_id, current_hp=result.current_hp,
                          max_hp=result.maximum_hp,
                          refresh_sheet=True)


def unlock_rank_response(character_id, command):
    try:
        result = rank_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return rank_unlocked_success(result)


def rank_unlocked_success(result):
    return saved_response(f"Rang {result.rank} débloqué.", character_id=result.character_id,
                          refresh_sheet=True)


def level_up_success(character_id, result):
    message = f"Niveau {result.level} atteint : 1 point de voie gagné."
    return saved_response(message, character_id=character_id, current_hp=result.current_hp,
                          max_hp=result.maximum_hp, refresh_sheet=True)


def raise_character_level(character_id):
    try:
        result = progression_service().execute(character_id, not is_gm())
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return level_up_success(character_id, result)


def progression_service():
    return RaiseLevel(SqliteProgressionRepository(get_db()))


def rank_service():
    return UnlockRank(SqliteProgressionRepository(get_db()))


def action_service():
    return UseAction(SqliteProgressionRepository(get_db()), RandomDiceRoller())


def racial_bonus_service():
    return ChooseRacialBonus(SqliteProgressionRepository(get_db()))


def use_action_response(character_id, command):
    try:
        result = action_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return used_action_success(result)


def used_action_success(result):
    key = f"{result.path_type}:{result.path_id}:{result.rank}"
    return saved_response(f"{result.name} utilisée.", character_id=result.character_id,
                          action_key=key, remaining=result.remaining,
                          current_hp=result.current_hp, max_hp=result.maximum_hp,
                          automated=result.automated)


@bp.post("/<int:character_id>/bonus-racial")
def choose_racial_bonus(character_id):
    validate_csrf()
    path_id = form_integer("racial_path_id", "Bonus racial invalide.")
    return choose_bonus_response(character_id, RacialBonusCommand(path_id))
@bp.post("/<int:character_id>/rangs")
def unlock_rank(character_id):
    validate_csrf()
    path_type = request.form.get("path_type", "")
    path_id = form_integer("path_id", "Voie invalide.")
    return unlock_rank_response(character_id, RankCommand(path_type, path_id))


@bp.post("/<int:character_id>/voie-personnelle/<int:rank>")
def update_custom_path_rank(character_id, rank):
    validate_csrf()
    character = accessible_character(character_id)
    if character["character_type"] != "player" or rank not in range(1, 6):
        abort(400, "Cette voie personnelle n’est pas disponible.")
    try:
        description = optional_text("description", 2000)
    except ValueError as error:
        abort(400, str(error))
    database = get_db()
    database.execute(
        "INSERT INTO character_custom_rank (character_id,rank,description) VALUES (?,?,?) "
        "ON CONFLICT(character_id,rank) DO UPDATE SET description=excluded.description",
        (character_id, rank, description),
    )
    database.commit()
    return saved_response("Voie personnelle mise à jour.", character_id=character_id,
                          refresh_sheet=True, close_dialog=True)


@bp.post("/<int:character_id>/degats-mortels")
def update_mortal_damage(character_id):
    validate_csrf()
    accessible_character(character_id)
    value = form_integer("mortal_damage", "Compteur de dégâts mortels invalide.")
    if value not in range(4):
        abort(400, "Le compteur de dégâts mortels doit être compris entre 0 et 3.")
    database = get_db()
    database.execute(
        "UPDATE character SET mortal_damage=?,version=version+1,"
        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (value, character_id),
    )
    database.commit()
    message = "Le personnage est mort." if value == 3 else f"Dégâts mortels : {value}/3."
    return saved_response(message, character_id=character_id, refresh_sheet=True)


@bp.post("/<int:character_id>/ames")
def update_souls(character_id):
    validate_csrf()
    accessible_character(character_id)
    value = form_integer("souls", "Compteur d’âmes invalide.")
    if value < 0:
        abort(400, "Le nombre d’âmes ne peut pas être négatif.")
    database = get_db()
    database.execute(
        "UPDATE character SET souls=?,version=version+1,"
        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (value, character_id),
    )
    database.commit()
    return saved_response(f"Âmes : {value}.", character_id=character_id,
                          refresh_sheet=True)
@bp.post("/<int:character_id>/niveau")
def level_up(character_id):
    validate_csrf()
    return raise_character_level(character_id)
@bp.post("/<int:character_id>/pv")
def update_hp(character_id):
    validate_csrf()
    return change_health(character_id, health_command())


def change_health(character_id, command):
    try:
        result = health_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return health_response(result)


def health_service():
    return ChangeHealth(SqliteHealthRepository(get_db()))


def health_command():
    """La Défense n'est plus reçue du client : elle est recalculée au moment du coup."""
    return HealthCommand(request.form.get("action", ""), request.form.get("amount", ""),
                         request.form.get("damage_type", "physical"))


def application_failure(error):
    status = application_error_status(error)
    if asynchronous_request():
        return jsonify(ok=False, message=str(error)), status
    abort(status, str(error))


def application_error_status(error):
    statuses = {ResourceNotFound: 404, ConcurrentUpdate: 409, RepositoryUnavailable: 503}
    return statuses.get(type(error), 400)


def health_response(result):
    values = {"character_id": result.character_id, "current_hp": result.current,
              "max_hp": result.maximum, "estus_available": result.estus_available,
              "refresh_sheet": result.refresh_sheet}
    return saved_response(f"PV mis à jour : {result.previous} → {result.current}.", **values)


@bp.post("/<int:character_id>/competences/utiliser")
def use_action(character_id):
    validate_csrf()
    path_type = request.form.get("path_type", "")
    path_id, rank = action_identifiers()
    return use_action_response(character_id, ActionCommand(path_type, path_id, rank))


def action_identifiers():
    return (form_integer("path_id", "Compétence invalide."),
            form_integer("rank", "Compétence invalide."))
def character_redirect(character_id):
    return redirect(url_for("main.character_detail", character_id=character_id))


@bp.get("/<int:character_id>/portrait")
def portrait(character_id):
    character = accessible_character(character_id)
    filename = character["portrait_filename"]
    return send_portrait(filename) if available_portrait(filename) else Response(status=204)


def available_portrait(filename):
    return bool(filename) and (Path(current_app.config["PORTRAIT_PATH"]) / filename).is_file()


def send_portrait(filename):
    return send_from_directory(current_app.config["PORTRAIT_PATH"], filename, max_age=86400)


@bp.post("/<int:character_id>/portrait")
def update_portrait(character_id):
    validate_csrf()
    character = accessible_character(character_id)
    uploaded = request.files.get("portrait")
    return store_portrait(character, uploaded.read()) if uploaded else missing_portrait()


def missing_portrait():
    return jsonify(ok=False, message="Choisis une image."), 400


def store_portrait(character, content):
    suffix = image_suffix(content)
    if not content or suffix is None:
        return jsonify(ok=False, message="Utilise une image PNG, JPEG ou WebP."), 400
    return persist_portrait_content(character, content, suffix)


def persist_portrait_content(character, content, suffix):
    filename = f"{uuid4().hex}{suffix}"
    portrait_directory = Path(current_app.config["PORTRAIT_PATH"])
    write_portrait(portrait_directory, filename, content)
    return finalize_portrait(character, portrait_directory, filename)


def finalize_portrait(character, directory, filename):
    persist_portrait(character["id"], filename)
    remove_old_portrait(directory, character["portrait_filename"])
    return portrait_response(character["id"])


def write_portrait(directory, filename, content):
    (directory / filename).write_bytes(content)


def image_suffix(content):
    known = next((extension for signature, extension in IMAGE_SIGNATURES
                  if content.startswith(signature)), None)
    return known or webp_suffix(content)


def webp_suffix(content):
    return ".webp" if len(content) >= 12 and content.startswith(
        b"RIFF") and content[8:12] == b"WEBP" else None


def persist_portrait(character_id, filename):
    database = get_db()
    database.execute(UPDATE_PORTRAIT_SQL, (filename, character_id))
    database.commit()


def remove_old_portrait(directory, filename):
    if filename:
        (directory / filename).unlink(missing_ok=True)


def portrait_response(character_id):
    image_url = url_for("characters.portrait", character_id=character_id)
    if asynchronous_request():
        return jsonify(ok=True, message="Portrait enregistré.", image_url=image_url)
    return character_redirect(character_id)


@bp.get("/<int:character_id>/equipement")
def equipment_index(character_id):
    character = accessible_character(character_id)
    equipment = equipment_for_character(get_db(), character_id)
    return render_template("characters/equipment.html", character=character,
                           equipment=equipment, item_types=ITEM_TYPES)


def show_equipment_create(character_id):
    return render_equipment_form(character_id, None)


def post_equipment_create(character_id):
    validate_csrf()
    _result, error = equipment_attempt(create_from_form, character_id)
    if error:
        return rejected_equipment(error, show_equipment_create, character_id)
    return equipment_saved_response("Objet ajouté.", character_id)


def create_from_form(character_id):
    values = equipment_values(request.form, valid_item_icon_path)
    return save_item_service().execute(character_id, not is_gm(),
                                       SaveItemCommand(values)).equipment_id


def equipment_attempt(operation, *arguments):
    try:
        return operation(*arguments), None
    except (ValueError, ApplicationError) as error:
        return None, error


def rejected_equipment(error, renderer, *arguments):
    get_db().rollback()
    if asynchronous_request():
        # Sans cela le client recevait du HTML et affichait le titre de la page en message.
        return jsonify(ok=False, message=str(error)), application_error_status(error)
    flash(str(error), "error")
    return renderer(*arguments)


def equipment_saved_response(message, character_id, equipment_id=None):
    if not asynchronous_request() and equipment_return_requested():
        flash(message, "success")
        return redirect(url_for("characters.equipment_index", character_id=character_id))
    return saved_response(message, character_id=character_id,
                          selected_item_id=equipment_id, refresh_sheet=True)


def equipment_return_requested():
    return request.form.get("return_to") == "equipment" or request.args.get("return_to") == "equipment"


def render_equipment_form(character_id, equipment):
    return render_template("characters/equipment_form.html", character_id=character_id,
                           equipment=equipment, item_types=ITEM_TYPES)


EQUIPMENT_CREATE_HANDLERS = {"GET": show_equipment_create, "POST": post_equipment_create}
@bp.route("/<int:character_id>/equipement/nouveau", methods=("GET", "POST"))
def equipment_create(character_id):
    accessible_character(character_id)
    return EQUIPMENT_CREATE_HANDLERS[request.method](character_id)


def show_equipment_edit(character_id, equipment):
    return render_equipment_form(character_id, equipment)


def post_equipment_edit(character_id, equipment):
    validate_csrf()
    _result, error = equipment_attempt(update_from_form, character_id, equipment.id)
    if error:
        return rejected_equipment(error, reload_equipment_form, character_id, equipment.id)
    return equipment_saved_response("Objet mis à jour.", character_id, equipment.id)


def update_from_form(character_id, equipment_id):
    values = equipment_values(request.form, valid_item_icon_path)
    command = SaveItemCommand(values, equipment_id)
    return save_item_service().execute(character_id, not is_gm(), command)


def reload_equipment_form(character_id, equipment_id):
    return render_equipment_form(character_id, accessible_equipment(character_id, equipment_id))


EQUIPMENT_EDIT_HANDLERS = {"GET": show_equipment_edit, "POST": post_equipment_edit}


def accessible_equipment(character_id, equipment_id):
    accessible_character(character_id)
    equipment = find_equipment(get_db(), character_id, equipment_id)
    if equipment is None:
        abort(404)
    return equipment
@bp.post("/<int:character_id>/equipement/rapide")
def equipment_quick_create(character_id):
    validate_csrf()
    command = QuickCreateCommand(request.form.get("item_type", ""))
    return create_quick_item(character_id, command)


def create_quick_item(character_id, command):
    try:
        result = quick_create_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return quick_create_response(result.character_id, result.equipment_id)


def quick_create_response(character_id, equipment_id):
    return saved_response("Objet créé. Renseigne maintenant sa fiche.",
                          character_id=character_id, selected_item_id=equipment_id,
                          refresh_sheet=True)
@bp.route(
    "/<int:character_id>/equipement/<int:equipment_id>/modifier",
    methods=("GET", "POST"),
)
def equipment_edit(character_id, equipment_id):
    equipment = accessible_equipment(character_id, equipment_id)
    return EQUIPMENT_EDIT_HANDLERS[request.method](character_id, equipment)
@bp.post("/<int:character_id>/equipement/<int:equipment_id>/supprimer")
def equipment_delete(character_id, equipment_id):
    validate_csrf()
    return delete_item(character_id, DeleteCommand(equipment_id))


def delete_item(character_id, command):
    try:
        result = delete_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return saved_response("Objet supprimé.", character_id=result.character_id,
                          refresh_sheet=True)
@bp.post("/<int:character_id>/equipement/<int:equipment_id>/equiper")
def equipment_toggle(character_id, equipment_id):
    validate_csrf()
    return toggle_item(character_id, ToggleCommand(equipment_id))


def toggle_item(character_id, command):
    try:
        result = toggle_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    message = "Objet équipé." if result.equipped else "Objet retiré."
    return equipment_toggle_response(message, result.character_id, result.equipment_id)


def equipment_toggle_response(message, character_id, equipment_id):
    return saved_response(message, character_id=character_id,
                          selected_item_id=equipment_id, refresh_sheet=True)
@bp.post("/<int:character_id>/equipement/<int:equipment_id>/utiliser")
def equipment_use(character_id, equipment_id):
    validate_csrf()
    return consume_item(character_id, ConsumeCommand(equipment_id))


def consume_item(character_id, command):
    try:
        result = consume_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return saved_response(f"{result.name} utilisé.", character_id=result.character_id,
                          refresh_sheet=True)


def consume_service():
    return ConsumeItem(SqliteInventoryRepository(get_db()))


def toggle_service():
    return ToggleItem(SqliteInventoryRepository(get_db()))


def quick_create_service():
    return QuickCreateItem(SqliteInventoryRepository(get_db()))


def delete_service():
    return DeleteItem(SqliteInventoryRepository(get_db()))


def duplicate_service():
    return DuplicateItem(SqliteInventoryRepository(get_db()))


def save_item_service():
    return SaveItem(SqliteInventoryRepository(get_db()))


@bp.get("/icones/fichier/<path:icon_path>")
def item_icon(icon_path):
    try:
        valid_path = valid_item_icon_path(icon_path)
    except ValueError:
        abort(404)
    return send_from_directory(ITEM_ICON_ROOT, valid_path, max_age=86400)


@bp.get("/interface/<path:asset_path>")
def interface_asset(asset_path):
    try:
        candidate = interface_asset_path(INTERFACE_ASSET_ROOT, asset_path)
    except ValueError:
        abort(404)
    return send_from_directory(INTERFACE_ASSET_ROOT, candidate.name, max_age=86400)


@bp.get("/bibliotheque-icones/<item_type>")
def item_icon_library(item_type):
    directories = icon_directories(item_type, request.args.get("category"))
    page = requested_icon_page()
    selected, next_page = icon_page(ITEM_ICON_ROOT, directories, page)
    return icon_library_response(selected, next_page)


def icon_directories(item_type, category=None):
    directories = ITEM_ICON_DIRECTORIES.get(item_type)
    if directories is None:
        abort(404)
    if category:
        selected = ITEM_ICON_CATEGORIES.get(category)
        if selected is None:
            abort(404)
        return selected[1]
    return directories


def requested_icon_page():
    try:
        return page_number(request.args.get("page", "0"))
    except ValueError as error:
        abort(400, str(error))


def icon_library_response(paths, next_page):
    icons = [{"path": path, "url": url_for("characters.item_icon", icon_path=path)}
             for path in paths]
    return jsonify(ok=True, icons=icons, next_page=next_page)


@bp.post("/<int:character_id>/equipement/<int:equipment_id>/dupliquer")
def equipment_duplicate(character_id, equipment_id):
    validate_csrf()
    return duplicate_item(character_id, DuplicateCommand(equipment_id))


def duplicate_item(character_id, command):
    try:
        result = duplicate_service().execute(character_id, not is_gm(), command)
    except (InvalidRequest, ResourceNotFound, ConcurrentUpdate, RepositoryUnavailable) as error:
        return application_failure(error)
    return saved_response("Objet dupliqué.", character_id=result.character_id,
                          refresh_sheet=True)

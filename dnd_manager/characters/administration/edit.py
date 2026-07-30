from dnd_manager.characters.common.constitution import accessory_constitution
from dnd_manager.characters.common.players import find_or_create_owner
from dnd_manager.characters.common.rules import (
    adjusted_health,
    maximum_hp,
    valid_point_buy,
)
from dnd_manager.shared.catalog import ABILITY_FIELDS, CHARACTER_TYPES, VISIBILITIES
from dnd_manager.shared.errors import ConcurrentUpdate

UPDATE_SQL = """
UPDATE character SET name = :name, owner_id = :owner_id, species_id = :species_id,
    racial_path_id = :racial_path_id, character_type = :character_type,
    visibility = :visibility, level = :level, current_hp = :current_hp,
    max_hp = :max_hp, strength = :strength, dexterity = :dexterity,
    constitution = :constitution, intelligence = :intelligence,
    wisdom = :wisdom, charisma = :charisma, version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND version = :version
"""


def update_character(database, character, form):
    values = edit_values(database, character, form)
    cursor = database.execute(UPDATE_SQL, values)
    ensure_current_version(database, cursor)
    clear_changed_species(database, character, values)
    database.commit()


def edit_values(database, character, form):
    values = parsed_values(form, character)
    values["racial_path_id"] = racial_path_id(database, character, values["species_id"])
    values["owner_id"] = resolve_owner(database, form)
    values.update(health_values(database, character, values))
    return values


def parsed_values(form, character):
    values = identity_values(form)
    values.update(integer_values(form, character))
    values.update(choice_values(form))
    validate_values(values, character)
    return values


def choice_values(form):
    return {"character_type": form.get("character_type", ""),
            "visibility": form.get("visibility", "")}


def identity_values(form):
    name = form.get("name", "").strip()
    validate_name(name)
    return {"name": name}


def validate_name(name):
    if not name:
        raise ValueError("Le champ « name » est obligatoire.")
    if len(name) > 80:
        raise ValueError("Le champ « name » ne peut pas dépasser 80 caractères.")


def integer_values(form, character):
    try:
        return parsed_integers(form, character)
    except ValueError as error:
        raise ValueError("Le niveau, l'espèce et les caractéristiques doivent être valides.") from error


def parsed_integers(form, character):
    values = {"level": int(form.get("level", "")), "species_id": int(form.get("species_id", "")),
              "version": int(form.get("version", str(character["version"])))}
    values.update({field: int(form.get(field, "")) for field in ABILITY_FIELDS})
    return {"id": character["id"], **values}


def validate_values(values, character):
    validate_choice(values["character_type"], CHARACTER_TYPES, "Type de personnage invalide.")
    validate_choice(values["visibility"], VISIBILITIES, "Visibilité invalide.")
    validate_level(values["level"], character["level"])
    validate_scores(values)


def validate_choice(value, choices, message):
    if value not in choices:
        raise ValueError(message)


def validate_level(level, current_level):
    if not current_level <= level <= 20:
        raise ValueError("Le niveau ne peut pas diminuer et doit rester inférieur ou égal à 20.")


def validate_scores(values):
    if not valid_point_buy(values[field] for field in ABILITY_FIELDS):
        raise ValueError("Les caractéristiques doivent utiliser exactement 27 points.")


def racial_path_id(database, character, species_id):
    require_species(database, species_id)
    if species_id != character["species_id"]:
        return None
    return valid_racial_path(database, character["racial_path_id"], species_id)


def require_species(database, species_id):
    row = database.execute("SELECT id FROM species WHERE id = ?", (species_id,)).fetchone()
    if row is None:
        raise ValueError("L'espèce sélectionnée n'est pas disponible.")


def valid_racial_path(database, path_id, species_id):
    if not path_id:
        return None
    query = "SELECT id FROM racial_path WHERE id = ? AND species_id = ? AND configured = 1"
    row = database.execute(query, (path_id, species_id)).fetchone()
    return path_id if row else None


def resolve_owner(database, form):
    owner_name = form.get("owner_name", "").strip()
    if len(owner_name) > 80:
        raise ValueError("Le nom du propriétaire ne peut pas dépasser 80 caractères.")
    return find_or_create_owner(database, owner_name) if owner_name else None


def health_values(database, character, values):
    racial_bonus = racial_constitution(database, values["racial_path_id"])
    accessory_bonus = accessory_constitution(database, character["id"])
    new_maximum = edited_maximum(character, values, racial_bonus, accessory_bonus)
    return {"max_hp": new_maximum, "current_hp": adjusted_health(
            character["current_hp"], character["max_hp"], new_maximum)}


def edited_maximum(character, values, racial_bonus, accessory_bonus):
    constitution = values["constitution"] + character["class_constitution_bonus"]
    return maximum_hp(character["hit_die"], values["level"],
                      constitution + racial_bonus + accessory_bonus)


def racial_constitution(database, path_id):
    if not path_id:
        return 0
    row = database.execute("SELECT constitution_bonus FROM racial_path WHERE id = ?",
                           (path_id,)).fetchone()
    return row["constitution_bonus"] if row else 0


def ensure_current_version(database, cursor):
    """Erreur métier typée : la traduction en HTTP appartient au blueprint."""
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("La fiche a été modifiée simultanément. Recharge la page.")


def clear_changed_species(database, character, values):
    if values["species_id"] != character["species_id"]:
        database.execute("DELETE FROM character_rank WHERE character_id = ? "
                         "AND path_type = 'racial'", (character["id"],))

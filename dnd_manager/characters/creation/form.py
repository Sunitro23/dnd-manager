from dnd_manager.characters.common.players import find_or_create_owner
from dnd_manager.characters.common.rules import maximum_hp, point_buy_total, valid_point_buy
from dnd_manager.shared.catalog import (
    ABILITY_FIELDS,
    CHARACTER_TYPES,
    VISIBILITIES,
)


def required_text(form, name, maximum):
    value = optional_text(form, name, maximum)
    if not value:
        raise ValueError(f'Le champ « {name} » est obligatoire.')
    return value


def optional_text(form, name, maximum):
    value = form.get(name, "").strip()
    if len(value) > maximum:
        raise ValueError(f'Le champ « {name} » ne peut pas dépasser {maximum} caractères.')
    return value


def catalogue_options(database):
    classes = configured_rows(database, "character_class", "*")
    species = configured_rows(database, "species", "id, name")
    players = ordered_rows(database, "player", "id, display_name", "display_name")
    return classes, species, players


def configured_rows(database, table, columns):
    return ordered_rows(database, table, columns, "name", "WHERE configured = 1")


def ordered_rows(database, table, columns, order, condition=""):
    query = f"SELECT {columns} FROM {table} {condition} ORDER BY {order} COLLATE NOCASE"
    return database.execute(query).fetchall()


def catalogue_item(database, table, item_id):
    validate_catalogue(table)
    item = database.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ValueError("La classe ou l'espèce sélectionnée n'est plus disponible.")
    return item


def validate_catalogue(table):
    if table not in {"character_class", "species"}:
        raise ValueError("Catalogue inconnu.")


def character_values(database, form, gm):
    identity = identity_values(form)
    catalogues = catalogue_values(database, form)
    scores = ability_scores(form)
    administration = administration_values(form, gm)
    return assembled_values(database, form, identity, catalogues, scores, administration)


def identity_values(form):
    return {"name": required_text(form, "name", 80),
            "description": optional_text(form, "description", 4000),
            "personal_info": optional_text(form, "personal_info", 4000)}


def catalogue_values(database, form):
    class_id, species_id = required_catalogue_ids(form)
    class_item = catalogue_item(database, "character_class", class_id)
    catalogue_item(database, "species", species_id)
    return {"class_id": class_id, "species_id": species_id, "class_item": class_item}


def required_catalogue_ids(form):
    try:
        return int(form.get("class_id", "")), int(form.get("species_id", ""))
    except ValueError as error:
        raise ValueError("Une classe et une espèce sont obligatoires.") from error


def ability_scores(form):
    try:
        scores = {field: int(form.get(field, "")) for field in ABILITY_FIELDS}
    except ValueError as error:
        raise ValueError("Les six caractéristiques doivent être renseignées.") from error
    return validated_scores(scores)


def validated_scores(scores):
    if not valid_point_buy(scores.values()):
        spent = point_buy_total(scores.values())
        raise ValueError(f"Les caractéristiques doivent utiliser exactement 27 points "
                         f"(total actuel : {spent}).")
    return scores


def administration_values(form, gm):
    if not gm:
        return {"character_type": "player", "visibility": "campaign", "level": 1}
    values = {"character_type": form.get("character_type", ""),
              "visibility": form.get("visibility", ""), "level": level_value(form)}
    return validated_administration(values)


def level_value(form):
    try:
        return int(form.get("level", "1"))
    except ValueError as error:
        raise ValueError("Le niveau doit être un nombre entier.") from error


def validated_administration(values):
    validate_character_type(values["character_type"])
    validate_visibility(values["visibility"])
    validate_level(values["level"])
    return values


def validate_character_type(character_type):
    if character_type not in CHARACTER_TYPES:
        raise ValueError("Type de personnage invalide.")


def validate_visibility(visibility):
    if visibility not in VISIBILITIES:
        raise ValueError("Visibilité invalide.")


def validate_level(level):
    if not 1 <= level <= 20:
        raise ValueError("Le niveau doit être compris entre 1 et 20.")


def assembled_values(database, form, identity, catalogues, scores, administration):
    maximum = character_maximum(catalogues["class_item"], scores, administration["level"])
    relationships = relationship_values(database, form, catalogues)
    health = {"current_hp": maximum, "max_hp": maximum}
    return {**relationships, **identity, **administration, **scores, **health}


def relationship_values(database, form, catalogues):
    return {"owner_id": resolve_owner(database, form), "class_id": catalogues["class_id"],
            "species_id": catalogues["species_id"], "class_path_id": None,
            "racial_path_id": None}


def resolve_owner(database, form):
    owner_name = optional_text(form, "owner_name", 80)
    return find_or_create_owner(database, owner_name) if owner_name else None




def character_maximum(class_item, scores, level):
    constitution = scores["constitution"] + class_item["constitution_bonus"]
    return maximum_hp(class_item["hit_die"], level, constitution)

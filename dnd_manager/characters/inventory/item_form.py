from dnd_manager.characters.common.constitution import (
    accessory_constitution_column,
    effective_constitution,
)
from dnd_manager.characters.common.rules import adjusted_health, maximum_hp
from dnd_manager.characters.inventory.contracts import ItemData
from dnd_manager.shared.errors import ConcurrentUpdate, InvalidRequest
from dnd_manager.shared.catalog import EQUIPMENT_SLOTS, ITEM_TYPES

TEXT_FIELDS = {
    "name": (100, True), "damage_dice": (50, False), "damage_type": (50, False),
    "uses": (80, False), "stat": (30, False), "icon_path": (200, False),
    "effect": (300, False), "notes": (2000, False),
}
NUMERIC_FIELDS = ("physical_bonus", "elemental_bonus", "spiritual_bonus", "stat_bonus")
OCCUPIED_SLOTS_SQL = (
    "SELECT slot FROM equipment WHERE character_id = ? AND equipped = 1 "
    "AND slot != '' AND (? IS NULL OR id != ?)"
)
HP_SOURCE_SQL = f"""
SELECT c.level, c.constitution, c.current_hp, c.max_hp, c.version, cc.hit_die,
       cc.constitution_bonus AS class_constitution_bonus,
       COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus,
       {accessory_constitution_column()}
FROM character c JOIN character_class cc ON cc.id = c.class_id
LEFT JOIN racial_path rp ON rp.id = c.racial_path_id WHERE c.id = ?
"""
UPDATE_HEALTH_SQL = """
UPDATE character SET current_hp = ?, max_hp = ?,
    version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE id = ? AND version = ?
"""


def equipment_values(form, icon_validator):
    item_type = valid_item_type(form.get("item_type", ""))
    values = common_values(form, item_type, icon_validator)
    normalize_values(values)
    return ItemData(**values)


def valid_item_type(item_type):
    if item_type not in ITEM_TYPES:
        raise ValueError("Type d'objet invalide.")
    return item_type


def common_values(form, item_type, icon_validator):
    values = text_values(form)
    values.update(form_metadata(form, item_type))
    values["icon_path"] = icon_validator(values["icon_path"])
    return values


def form_metadata(form, item_type):
    return {**numeric_values(form, item_type), "item_type": item_type,
            "equipped": int(form.get("equipped") == "1")}


def text_values(form):
    return {
        name: text_value(form, name, maximum, required)
        for name, (maximum, required) in TEXT_FIELDS.items()
    }


def text_value(form, name, maximum, required):
    value = form.get(name, "").strip()
    require_text(name, value, required)
    require_text_length(name, value, maximum)
    return value


def require_text_length(name, value, maximum):
    if len(value) > maximum:
        raise ValueError(f"Le champ « {name} » ne peut pas dépasser {maximum} caractères.")


def require_text(name, value, required):
    if required and not value:
        raise ValueError(f"Le champ « {name} » est obligatoire.")


def numeric_values(form, item_type):
    quantity = quantity_value(form, item_type)
    require_positive_quantity(quantity)
    numbers = {field: integer_value(form, field, 0) for field in NUMERIC_FIELDS}
    return {"quantity": quantity, **numbers}


def quantity_value(form, item_type):
    return integer_value(form, "quantity", 1) if item_type in {"consumable", "quest"} else 1


def integer_value(form, name, default):
    try:
        return int(form.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"Le champ « {name} » doit être un nombre entier.") from error


def require_positive_quantity(quantity):
    if quantity < 1:
        raise ValueError("La quantité doit être supérieure ou égale à 1.")


def normalize_values(values):
    NORMALIZERS.get(values["item_type"], clear_all_specific)(values)


def armor_values(values):
    clear_damage(values)
    clear_spell(values)
    clear_stat(values)


def weapon_values(values):
    clear_defenses(values)
    clear_spell(values)
    clear_stat(values)


def spell_values(values):
    clear_defenses(values)
    clear_stat(values)


def accessory_values(values):
    clear_defenses(values)
    clear_damage(values)
    clear_spell(values)


def clear_all_specific(values):
    clear_defenses(values)
    clear_damage(values)
    clear_spell(values)
    clear_stat(values)


def clear_defenses(values):
    for field in ("physical_bonus", "elemental_bonus", "spiritual_bonus"):
        values[field] = 0


def clear_damage(values):
    values["damage_dice"] = ""
    values["damage_type"] = ""


def clear_spell(values):
    values["uses"] = ""


def clear_stat(values):
    values["stat"] = ""
    values["stat_bonus"] = 0


NORMALIZERS = {
    "armor": armor_values,
    "shield": armor_values,
    "weapon": weapon_values,
    "spell": spell_values,
    "accessory": accessory_values,
}


def recalculate_hp(database, character_id):
    character = database.execute(HP_SOURCE_SQL, (character_id,)).fetchone()
    if character is None:
        raise InvalidRequest("Personnage introuvable ou sans classe.")
    maximum = equipment_maximum(character)
    current = adjusted_health(character["current_hp"], character["max_hp"], maximum)
    persist_health(database, character_id, current, maximum, character["version"])


def persist_health(database, character_id, current, maximum, version):
    """Respecte le verrou optimiste : deux éditions simultanées ne s'écrasent plus."""
    cursor = database.execute(UPDATE_HEALTH_SQL, (current, maximum, character_id, version))
    if cursor.rowcount == 0:
        raise ConcurrentUpdate("La fiche a été modifiée simultanément. Recharge la page.")


def equipment_maximum(character):
    """Doit rester aligné sur `character_maximum` : mêmes sources de bonus."""
    return maximum_hp(character["hit_die"], character["level"],
                      effective_constitution(character))


def first_available_slot(database, character_id, item_type, equipment_id=None):
    slots = EQUIPMENT_SLOTS.get(item_type, ())
    occupied = occupied_slots(database, character_id, equipment_id)
    return next((slot for slot in slots if slot not in occupied), None)


def occupied_slots(database, character_id, equipment_id):
    values = (character_id, equipment_id, equipment_id)
    rows = database.execute(OCCUPIED_SLOTS_SQL, values).fetchall()
    return {row["slot"] for row in rows}


def normalize_slot(database, character_id, equipment_id, item_type, equipped):
    operation = keep_or_assign if equipped else unequip_slot
    return operation(database, character_id, equipment_id, item_type)


def unequip_slot(database, _character_id, equipment_id, _item_type):
    return unequip(database, equipment_id)


def keep_or_assign(database, character_id, equipment_id, item_type):
    current = current_slot(database, equipment_id)
    if current in EQUIPMENT_SLOTS.get(item_type, ()):
        return current
    return assign_slot(database, character_id, equipment_id, item_type)


def unequip(database, equipment_id):
    database.execute(
        "UPDATE equipment SET equipped = 0, slot = '' WHERE id = ?", (equipment_id,)
    )
    return None


def current_slot(database, equipment_id):
    return database.execute(
        "SELECT slot FROM equipment WHERE id = ?", (equipment_id,)
    ).fetchone()["slot"]


def assign_slot(database, character_id, equipment_id, item_type):
    slot = first_available_slot(database, character_id, item_type, equipment_id)
    persist_slot(database, equipment_id, slot)
    return slot


def persist_slot(database, equipment_id, slot):
    database.execute(
        "UPDATE equipment SET equipped = ?, slot = ? WHERE id = ?",
        (int(bool(slot)), slot or "", equipment_id),
    )

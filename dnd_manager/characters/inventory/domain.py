from dnd_manager.characters.common.health import adjusted_health, maximum_hp
from dataclasses import replace

from dnd_manager.characters.inventory.contracts import (
    ConsumeResult,
    DeleteResult,
    ToggleResult,
)
from dnd_manager.shared.errors import InvalidRequest


def consume(state):
    require_consumable(state.item_type)
    require_quantity(state.quantity)
    return ConsumeResult(state.character_id, state.equipment_id, state.name,
                         state.quantity - 1)


def require_consumable(item_type):
    if item_type != "consumable":
        raise InvalidRequest("Seul un consommable peut être utilisé.")


def require_quantity(quantity):
    if quantity < 1:
        raise InvalidRequest("Ce consommable est épuisé.")


EQUIPMENT_SLOTS = {
    "weapon": ("right_hand", "left_hand"),
    "shield": ("right_hand", "left_hand"),
    "tool": ("right_hand", "left_hand"),
    "armor": ("armor",),
    "accessory": ("ring_1", "ring_2", "ring_3", "ring_4"),
}
QUICK_LABELS = {
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


def toggle(state):
    equipped = not state.equipped
    slot = target_slot(state, equipped)
    maximum = toggled_maximum(state, equipped)
    current = adjusted_health(state.current_hp, state.maximum_hp, maximum)
    return ToggleResult(state.character_id, state.equipment_id, equipped, slot,
                        current, maximum)


def target_slot(state, equipped):
    if not equipped:
        return ""
    return available_slot(state)


def available_slot(state):
    compatible = EQUIPMENT_SLOTS.get(state.item_type)
    require_equippable(compatible)
    available = first_available_slot(compatible, state.occupied_slots)
    require_available_slot(available)
    return available


def first_available_slot(compatible, occupied):
    return next((slot for slot in compatible if slot not in occupied), None)


def require_equippable(slots):
    if slots is None:
        raise InvalidRequest("Ce type d’objet ne peut pas être équipé.")


def require_available_slot(slot):
    if slot is None:
        raise InvalidRequest("Tous les emplacements compatibles sont déjà occupés.")


def toggled_maximum(state, equipped):
    constitution = state.constitution + toggled_constitution_bonus(state, equipped)
    return maximum_hp(state.hit_die, state.level, constitution)


def toggled_constitution_bonus(state, equipped):
    delta = state.item_stat_bonus if state.item_type == "accessory" and state.item_stat == "CON" else 0
    return state.constitution_bonus + (delta if equipped else -delta)


def quick_item_name(item_type):
    name = QUICK_LABELS.get(item_type)
    if name is None:
        raise InvalidRequest("Type d’objet invalide.")
    return name


def delete_item(state):
    maximum = toggled_maximum(state, False) if state.equipped else state.maximum_hp
    current = adjusted_health(state.current_hp, state.maximum_hp, maximum)
    return DeleteResult(state.character_id, state.equipment_id, current, maximum)


def duplicate_item(item):
    return replace(item, name=f"{item.name} — copie")

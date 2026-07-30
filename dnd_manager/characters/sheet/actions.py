from dnd_manager.characters.common.rules import limited_uses
from dnd_manager.shared.catalog import ABILITY_ABBREVIATIONS, ABILITY_LABELS

MODIFIER_LABELS = {
    "Force": "strength", "Dextérité": "dexterity", "Constitution": "constitution",
    "Intelligence": "intelligence", "Sagesse": "wisdom", "Charisme": "charisma",
}
DAMAGE_TYPES = {
    "physical": "physiques", "elemental": "élémentaires", "spiritual": "spirituels",
}
STAT_LABELS = {abbreviation: ABILITY_LABELS[field]
               for abbreviation, field in ABILITY_ABBREVIATIONS.items()}


def sheet_actions(paths, unlocked, uses, modifiers, equipment, equipped):
    actions, passives = path_entries(paths, unlocked, uses, modifiers)
    actions.extend(inventory_actions(equipment))
    passives.extend(inventory_passives(equipped))
    return actions, passives


def path_entries(paths, unlocked, uses, modifiers):
    actions, passives = [], []
    for path in paths:
        collect_path_entries(actions, passives, path, unlocked, uses, modifiers)
    return actions, passives


def collect_path_entries(actions, passives, path, unlocked, uses, modifiers):
    key = path_key(path)
    for rank in path["ranks"]:
        decorate_rank(rank, modifiers)
        collect_unlocked_rank(actions, passives, path, rank, unlocked[key], uses)


def path_key(path):
    return f"{path['path_type']}:{path['id']}"


def decorate_rank(rank, modifiers):
    active, passive = rank.get("active"), rank.get("passive")
    rank["_active_effect"] = personalized_effect(active["effect"], modifiers) if active else None
    rank["_active_uses"] = personalized_uses(active["uses"]) if active else None
    rank["_passive_effect"] = personalized_effect(passive["effect"], modifiers) if passive else None


def personalized_effect(effect, modifiers):
    for label, field in MODIFIER_LABELS.items():
        effect = replace_modifier(effect, label, modifiers[field])
    return effect


def replace_modifier(effect, label, modifier):
    signed = f"+ {modifier}" if modifier >= 0 else f"- {abs(modifier)}"
    effect = effect.replace(f"+ MOD {label}", signed)
    return effect.replace(f"MOD {label}", f"{modifier:+d}")


def personalized_uses(uses):
    for count in (1, 2, 3):
        plural = "s" if count > 1 else ""
        uses = uses.replace(f"{count} fois par Repos au Feu",
                            f"{count} utilisation{plural} avant repos")
    return uses.replace("3 charges par Repos au Feu", "3 charges avant repos")


def collect_unlocked_rank(actions, passives, path, rank, unlocked, uses):
    if rank["rank"] not in unlocked:
        return
    append_active(actions, path, rank, uses)
    append_passive(passives, path, rank)


def append_active(actions, path, rank, uses):
    active = rank.get("active")
    if active:
        actions.append(active_entry(path, rank, active, uses))


def active_entry(path, rank, active, uses):
    limit = limited_uses(active["uses"])
    spent = uses.get((path["path_type"], path["id"], rank["rank"]), 0)
    remaining = max(0, limit - spent) if limit is not None else None
    return active_values(path, rank, active, limit, remaining)


def active_values(path, rank, active, limit, remaining):
    displayed_uses = f"{remaining}/{limit} restantes" if limit is not None else rank["_active_uses"]
    key = f"{path['path_type']}:{path['id']}:{rank['rank']}"
    return active_details(path, rank, active, key, displayed_uses, remaining)


def active_details(path, rank, active, key, displayed_uses, remaining):
    return {"key": key, "path_type": path["path_type"], "path_id": path["id"],
            "rank": rank["rank"], "category": "Compétences", "source": path["name"],
            "name": rank["name"], "timing": active["timing"],
            "uses": displayed_uses, "remaining": remaining, "effect": rank["_active_effect"]}


def append_passive(passives, path, rank):
    passive = rank.get("passive")
    if passive:
        passives.append({"source": path["name"], "name": rank["name"],
                         "frequency": passive["frequency"],
                         "effect": rank["_passive_effect"]})


def inventory_actions(equipment):
    actions = []
    for item in equipment:
        append_inventory_action(actions, item)
    return actions


def append_inventory_action(actions, item):
    action = INVENTORY_ACTIONS.get(item.item_type, no_action)(item)
    if action:
        actions.append(action)


def spell_action(item):
    damage = spell_damage(item)
    effect = " · ".join(part for part in (damage, item.effect) if part)
    return inventory_action("Sorts", f"Lancer {item.name}", item.uses, effect)


def spell_damage(item):
    damage_type = DAMAGE_TYPES.get(item.damage_type, item.damage_type)
    return f"{item.damage_dice} dégâts {damage_type}" if item.damage_dice else ""


def consumable_action(item):
    if not item.equipped:
        return None
    # `equipment_id` rend l'action déclenchable : sans lui, la fiche affichait
    # « Utiliser … » sans aucun bouton et l'objet ne pouvait pas être consommé.
    return inventory_action("Consommables", f"Utiliser {item.name}",
                            f"×{item.quantity}", item.effect, equipment_id=item.id)


def no_action(_item):
    return None


def inventory_action(category, name, uses, effect, equipment_id=None):
    action = {"category": category, "source": "Inventaire", "name": name,
              "timing": "Objet", "uses": uses,
              "effect": effect or "Aucun effet renseigné."}
    return action if equipment_id is None else action | {"equipment_id": equipment_id}


INVENTORY_ACTIONS = {"spell": spell_action, "consumable": consumable_action}


def inventory_passives(equipment):
    passives = []
    for item in equipment:
        append_inventory_passive(passives, item)
    return passives


def append_inventory_passive(passives, item):
    parts = passive_parts(item)
    if parts:
        passives.append(inventory_passive(item, parts))


def passive_parts(item):
    parts = defense_parts(item)
    append_stat_part(parts, item)
    append_tool_part(parts, item)
    return parts


def defense_parts(item):
    fields = (("physical_bonus", "Défense physique"),
              ("elemental_bonus", "Défense élémentaire"),
              ("spiritual_bonus", "Défense spirituelle"))
    return [f"{getattr(item, field):+d} {label}"
            for field, label in fields if getattr(item, field)]


def append_stat_part(parts, item):
    if item.stat and item.stat_bonus:
        parts.append(f"{item.stat_bonus:+d} {STAT_LABELS.get(item.stat, item.stat)}")


def append_tool_part(parts, item):
    if item.item_type == "tool" and item.effect:
        parts.append(item.effect)


def inventory_passive(item, parts):
    return {"source": "Inventaire", "name": item.name,
            "frequency": "Équipé", "effect": " · ".join(parts)}

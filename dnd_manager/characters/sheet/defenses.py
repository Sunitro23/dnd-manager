"""Détail affiché sous chaque Défense.

Le calcul de la valeur vit dans `common.profile`, partagé avec l'application des dégâts.
"""

from dnd_manager.characters.common.profile import DEFENSES
from dnd_manager.characters.common.rules import ability_modifier


def defense_breakdowns(profile):
    return {name: defense_breakdown(name, profile) for name in DEFENSES}


def defense_breakdown(name, profile):
    label, ability, equipment_field = DEFENSES[name]
    parts = [{"label": label, "value": ability_modifier(profile.effective_scores[ability])}]
    parts.extend(equipment_parts(profile.equipped, equipment_field))
    append_breakdown_bonuses(parts, name, profile.character,
                             profile.permanent_defense_bonuses[name])
    return parts


def append_breakdown_bonuses(parts, name, character, permanent):
    append_species_bonus(parts, name, character)
    append_path_bonus(parts, name, character)
    append_permanent_bonus(parts, permanent)


def equipment_parts(equipped, field):
    return [{"label": item.name, "value": getattr(item, field)}
            for item in equipped if getattr(item, field)]


def append_species_bonus(parts, name, character):
    bonus = character[f"species_{name}_bonus"]
    if bonus:
        parts.append({"label": f"Race · {character['species_name']}", "value": bonus})


def append_path_bonus(parts, name, character):
    bonus = character[f"path_{name}_bonus"]
    if bonus:
        parts.append({"label": f"Origine · {character['racial_bonus_name']}", "value": bonus})


def append_permanent_bonus(parts, bonus):
    if bonus:
        parts.append({"label": "Voies débloquées", "value": bonus})

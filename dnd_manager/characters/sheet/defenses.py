from dnd_manager.characters.common.rules import ability_modifier, defense

DEFENSES = {
    "physical": ("Constitution", "constitution", "physical_bonus"),
    "elemental": ("Intelligence", "intelligence", "elemental_bonus"),
    "spiritual": ("Sagesse", "wisdom", "spiritual_bonus"),
}


def defense_context(character, scores, equipped, permanent):
    values = {name: defense_value(name, character, scores, equipped, permanent)
              for name in DEFENSES}
    breakdowns = {name: defense_breakdown(name, character, scores, equipped, permanent)
                  for name in DEFENSES}
    return values, breakdowns


def defense_value(name, character, scores, equipped, permanent):
    _label, ability, equipment_field = DEFENSES[name]
    equipment = (getattr(item, equipment_field) for item in equipped)
    return (defense(scores[ability], equipment)
            + character[f"species_{name}_bonus"]
            + character[f"path_{name}_bonus"] + permanent[name])


def defense_breakdown(name, character, scores, equipped, permanent):
    label, ability, equipment_field = DEFENSES[name]
    parts = [{"label": label, "value": ability_modifier(scores[ability])}]
    parts.extend(equipment_parts(equipped, equipment_field))
    append_breakdown_bonuses(parts, name, character, permanent[name])
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

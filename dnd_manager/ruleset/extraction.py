import re

ABILITY_NAMES = {
    "Force": "strength", "Dextérité": "dexterity", "Constitution": "constitution",
    "Intelligence": "intelligence", "Sagesse": "wisdom", "Charisme": "charisma",
}
DAMAGE_NAMES = {
    "Physiques": "physical", "Physique": "physical", "Feu": "fire",
    "Foudre": "lightning", "Glace": "ice", "Lumière": "light",
    "Ténèbres": "dark", "Poison": "poison", "Magique": "magic",
    "spirituels": "spiritual", "élémentaires": "elemental",
}
DEFENSE_NAMES = {
    "physique": "physical", "élémentaire": "elemental", "spirituelle": "spiritual",
}
RESOURCE_NAMES = {
    "Humanité": "humanity", "Carcassage": "carcassage",
    "émotion": "emotion", "malédiction": "curse", "faute": "guilt",
}
MECHANICS = {
    "choice": r"\b(?:choisi|choisissez|au choix| ou )\b",
    "condition": r"\b(?:lorsque|quand|tant que|si)\b",
    "damage": r"\b(?:dégâts?|inflige|subit)\b",
    "damage_reduction": r"\b(?:réduit les dégâts|réduction|moitié des dégâts)\b",
    "defense_modifier": r"\bDéfense\b",
    "equipment": r"\b(?:arme|bouclier|armure|équipement)\b",
    "heal": r"\b(?:soigne|soins|récupère|régénère)\b",
    "immunity": r"\b(?:immunité|immunisé)\b",
    "movement": r"\b(?:déplac|vitesse|repousse|attire|téléport)\w*",
    "status": r"\b(?:Effray|Immobil|Empoisonn|Charm|Agripp|À terre|invisible)\w*",
    "summon": r"\b(?:anime|invoque|automate|leurre|cadavre)\w*",
    "temporary_hit_points": r"\bPV temporaires\b",
    "rest": r"\b(?:repos|campement|feu de camp)\b",
    "resource": r"\b(?:Humanité|Carcassage|émotion|malédiction)\w*",
    "critical": r"\bcritique\b",
    "saving_throw": r"\bsauvegarde\b",
}


def extract_facts(text):
    facts = {"dice": dice(text), "ability_modifiers": ability_modifiers(text),
             "distances": distances(text), "durations": durations(text),
             "defenses": defenses(text), "damage_types": damage_types(text),
             "saving_throws": saving_throws(text), "rest_triggers": rest_triggers(text),
             "resource_refs": resource_refs(text), "mechanics": mechanics(text)}
    return {key: value for key, value in facts.items() if value}


def operation_skeletons(facts):
    mechanics_values = facts.get("mechanics", ())
    operations = [operation_skeleton(name, facts) for name in mechanics_values]
    return operations or [{"type": "unclassified", "complete": False}]


def operation_skeleton(name, facts):
    return {"type": name, "complete": False, "inputs": operation_inputs(name, facts)}


def operation_inputs(name, facts):
    fields = input_fields(name)
    return {field: facts[field] for field in fields if field in facts}


def input_fields(name):
    mappings = {
        "damage": ("dice", "ability_modifiers", "damage_types", "defenses"),
        "damage_reduction": ("dice", "ability_modifiers"),
        "defense_modifier": ("defenses", "durations"),
        "heal": ("dice", "ability_modifiers", "durations"),
        "movement": ("distances", "durations"),
        "saving_throw": ("saving_throws",),
        "status": ("durations", "saving_throws"),
        "temporary_hit_points": ("dice", "ability_modifiers", "durations"),
        "rest": ("rest_triggers", "dice", "durations"),
        "resource": ("resource_refs",),
    }
    return mappings.get(name, ())


def dice(text):
    values = ((int(count), int(sides)) for count, sides in re.findall(r"(\d+)d(\d+)", text))
    return unique({"count": count, "sides": sides} for count, sides in values)


def ability_modifiers(text):
    names = re.findall(r"MOD\s+(Force|Dextérité|Constitution|Intelligence|Sagesse|Charisme)",
                       text, re.IGNORECASE)
    return unique(ABILITY_NAMES[canonical(name, ABILITY_NAMES)] for name in names)


def distances(text):
    return unique({"value": int(value), "unit": "meter"}
                  for value in re.findall(r"(\d+)\s*m(?:\b|ètre)", text, re.IGNORECASE))


def durations(text):
    values = re.findall(r"(?:pendant|durant)\s+(\d+)\s+tours?", text, re.IGNORECASE)
    result = [{"value": int(value), "unit": "turn"} for value in values]
    if re.search(r"\bpar tour\b|début de (?:chacun de )?ses tours", text, re.IGNORECASE):
        result.append({"frequency": "once_per_turn"})
    return unique(result)


def defenses(text):
    names = re.findall(r"Défense\s+(physique|élémentaire|spirituelle)", text, re.IGNORECASE)
    return unique(DEFENSE_NAMES[name.casefold()] for name in names)


def damage_types(text):
    pattern = "|".join(map(re.escape, DAMAGE_NAMES))
    names = re.findall(rf"\b({pattern})\b", text, re.IGNORECASE)
    return unique(DAMAGE_NAMES[canonical(name, DAMAGE_NAMES)] for name in names)


def saving_throws(text):
    pattern = "|".join(map(re.escape, ABILITY_NAMES))
    names = re.findall(rf"sauvegarde(?:\s+de)?\s+({pattern})", text, re.IGNORECASE)
    return unique({"ability": ABILITY_NAMES[canonical(name, ABILITY_NAMES)],
                   "difficulty": "undefined"} for name in names)


def rest_triggers(text):
    triggers = []
    if re.search(r"\brepos (?:long|au feu)\b", text, re.IGNORECASE):
        triggers.append("long_rest")
    if re.search(r"\brepos court\b", text, re.IGNORECASE):
        triggers.append("short_rest")
    if re.search(r"\bprochain repos\b(?!\s+(?:long|court|au feu))|\bpour un repos\b",
                 text, re.IGNORECASE):
        triggers.append("any_rest")
    return unique(triggers)


def resource_refs(text):
    pattern = "|".join(map(re.escape, RESOURCE_NAMES))
    names = re.findall(rf"\b({pattern})s?\b", text, re.IGNORECASE)
    return unique(RESOURCE_NAMES[canonical(name, RESOURCE_NAMES)] for name in names)


def mechanics(text):
    return [name for name, pattern in MECHANICS.items()
            if re.search(pattern, text, re.IGNORECASE)]


def canonical(value, mapping):
    return next(key for key in mapping if key.casefold() == value.casefold())


def unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result

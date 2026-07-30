ABILITY_LABELS = {
    "strength": "Force", "dexterity": "Dextérité", "constitution": "Constitution",
    "intelligence": "Intelligence", "wisdom": "Sagesse", "charisma": "Charisme",
}
STAT_LABELS = {
    "defense.physical": "Défense physique",
    "defense.elemental": "Défense élémentaire",
    "defense.spiritual": "Défense spirituelle",
    "movement.speed": "Vitesse",
    "initiative": "Initiative",
    "saving_throw.all": "toutes les sauvegardes",
}


def describe(resolution):
    return " ".join(describe_operation(value, resolution["targeting"])
                    for value in resolution["operations"])


def describe_operation(operation, targeting):
    descriptions = {"heal": describe_heal, "modify_stat": describe_modifier,
                    "attack_profile": describe_attack, "grant_movement": describe_movement,
                    "set_health_floor": describe_health_floor,
                    "bonus_damage": describe_bonus_damage,
                    "regeneration": describe_regeneration,
                    "grant_immunity": describe_immunity,
                    "auto_stabilize": describe_stabilize,
                    "temporary_health": describe_temporary_health,
                    "damage": describe_damage,
                    "extra_attack": describe_extra_attack,
                    "force_critical": describe_force_critical,
                    "reduce_damage": describe_reduce_damage,
                    "ignore_defense": describe_ignore_defense,
                    "forced_movement": describe_forced_movement,
                    "choice": describe_choice,
                    "multiply_stat": describe_multiplier,
                    "negate_attack": describe_negation}
    return descriptions[operation["type"]](operation, targeting)


def describe_heal(operation, targeting):
    formula = describe_formula(operation["value"])
    if targeting["selector"] == "self":
        return f"Vous récupérez {formula} PV."
    distance = targeting["area"]["distance"]["value"]
    return f"Chaque allié dans un rayon de {distance} m récupère {formula} PV."


def describe_formula(formula):
    parts = [f"{formula['dice']['count']}d{formula['dice']['sides']}"]
    parts.extend(describe_term(term) for term in formula.get("terms", ()))
    if formula.get("constant"):
        parts.append(str(formula["constant"]))
    return " + ".join(parts)


def describe_term(term):
    return f"MOD {ABILITY_LABELS[term['ability']]}"


def describe_modifier(operation, targeting):
    value = operation["value"]
    subject = modifier_subject(value, targeting["selector"])
    duration = describe_duration(operation.get("duration"))
    return f"{subject} {value:+d} en {STAT_LABELS[operation['stat']]}{duration}."


def modifier_subject(value, selector):
    if selector == "all":
        return "Chaque cible gagne" if value >= 0 else "Chaque cible subit"
    return "Vous gagnez" if value >= 0 else "Vous subissez"


def describe_attack(operation, _targeting):
    formula = describe_formula(operation["damage"])
    return f"Votre arme naturelle inflige {formula} dégâts physiques."


def describe_movement(operation, _targeting):
    speed = operation["speed"]["value"]
    return f"Vous obtenez une vitesse de vol de {speed} m."


def describe_health_floor(operation, _targeting):
    return f"Vos PV remontent à au moins {operation['value']}."


def describe_duration(duration):
    return f" pendant {duration['value']} tours" if duration else ""


def describe_bonus_damage(operation, _targeting):
    formula = describe_formula(operation["value"])
    frequency = " une fois par tour" if operation["frequency"] == "once_per_turn" else ""
    duration = describe_duration(operation.get("duration"))
    return f"Vos attaques infligent +{formula} dégâts{frequency}{duration}."


def describe_regeneration(operation, _targeting):
    formula = describe_formula(operation["value"])
    return f"Vous régénérez {formula} PV par tour{describe_duration(operation.get('duration'))}."


def describe_immunity(operation, _targeting):
    labels = {"fear": "la peur", "ordinary_disease": "les maladies ordinaires",
              "ordinary_poison": "les poisons ordinaires"}
    return f"Vous êtes immunisé contre {labels[operation['status']]}."


def describe_stabilize(_operation, _targeting):
    return "Vous vous stabilisez automatiquement."


def describe_temporary_health(operation, _targeting):
    formula = describe_formula(operation["value"])
    return f"Vous gagnez {formula} PV temporaires{describe_duration(operation.get('duration'))}."


def describe_damage(operation, _targeting):
    formula = describe_formula(operation["value"])
    timing = " au tour suivant" if operation.get("timing") == "next_turn" else ""
    return f"La cible subit {formula} dégâts {operation['damage_type']}{timing}."


def describe_extra_attack(operation, _targeting):
    duration = describe_duration(operation.get("duration"))
    return f"Vous gagnez {operation['count']} attaque supplémentaire{duration}."


def describe_force_critical(_operation, _targeting):
    return "Votre prochaine attaque est un coup critique."


def describe_reduce_damage(operation, _targeting):
    return f"Les dégâts sont réduits de {describe_formula(operation['value'])}."


def describe_ignore_defense(operation, _targeting):
    value = operation.get("value", "la moitié de la")
    return f"Votre attaque ignore {value} Défense {operation['defense']}."


def describe_forced_movement(operation, _targeting):
    return f"La cible est repoussée de {operation['distance']['value']} m."


def describe_choice(operation, targeting):
    labels = [describe_option(option, targeting) for option in operation["options"]]
    return "Choisissez un effet : " + " ; ".join(labels) + "."


def describe_option(option, targeting):
    effects = " ".join(describe_operation(value, targeting) for value in option["operations"])
    return f"{option.get('label', option['id'])} — {effects}"


def describe_multiplier(operation, _targeting):
    return f"Votre {STAT_LABELS[operation['stat']]} est multipliée par {operation['factor']}."


def describe_negation(_operation, _targeting):
    return "L’attaque est annulée sur un résultat de 5 ou 6 au d6."

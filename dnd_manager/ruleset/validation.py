from dnd_manager.shared.errors import InvalidRequest

SELECTORS = {"all", "self", "single", "multiple"}
OPERATION_TARGETS = {"selected", "self"}
OPERATION_VALIDATORS = {"heal": lambda feature_id, operation: validate_formula(
    feature_id, operation.get("value")),
    "modify_stat": lambda feature_id, operation: validate_modifier(feature_id, operation),
    "attack_profile": lambda feature_id, operation: validate_attack(feature_id, operation),
    "grant_movement": lambda feature_id, operation: validate_movement(feature_id, operation),
    "set_health_floor": lambda feature_id, operation: validate_health_floor(
        feature_id, operation),
    "bonus_damage": lambda feature_id, operation: validate_bonus_damage(
        feature_id, operation),
    "regeneration": lambda feature_id, operation: validate_regeneration(
        feature_id, operation),
    "grant_immunity": lambda feature_id, operation: validate_immunity(
        feature_id, operation),
    "auto_stabilize": lambda feature_id, operation: validate_optional_duration(
        feature_id, operation.get("duration")),
    "temporary_health": lambda feature_id, operation: validate_temporary_health(
        feature_id, operation),
    "damage": lambda feature_id, operation: validate_damage(feature_id, operation),
    "extra_attack": lambda feature_id, operation: validate_extra_attack(
        feature_id, operation),
    "force_critical": lambda _feature_id, _operation: None,
    "reduce_damage": lambda feature_id, operation: validate_formula(
        feature_id, operation.get("value")),
    "ignore_defense": lambda feature_id, operation: validate_ignore_defense(
        feature_id, operation),
    "forced_movement": lambda feature_id, operation: validate_forced_movement(
        feature_id, operation),
    "choice": lambda feature_id, operation: validate_choice(feature_id, operation),
    "multiply_stat": lambda feature_id, operation: validate_multiplier(
        feature_id, operation),
    "negate_attack": lambda feature_id, operation: validate_negation(
        feature_id, operation)}


def validate_engine_rules(rules):
    if not isinstance(rules, dict):
        raise InvalidRequest("Le registre engine doit être un objet.")
    for feature_id, resolution in rules.items():
        validate_resolution(feature_id, resolution)
    return rules


def validate_resolution(feature_id, resolution):
    require_mapping(resolution, feature_id)
    require_equal(resolution.get("support"), "full", f"Support de {feature_id}")
    validate_targeting(feature_id, resolution.get("targeting"))
    operations = resolution.get("operations")
    if not isinstance(operations, list) or not operations:
        raise InvalidRequest(f"Opérations manquantes pour {feature_id}.")
    for operation in operations:
        validate_operation(feature_id, operation)


def validate_targeting(feature_id, targeting):
    require_mapping(targeting, f"ciblage de {feature_id}")
    if targeting.get("selector") not in SELECTORS:
        raise InvalidRequest(f"Sélecteur invalide pour {feature_id}.")
    if targeting.get("selector") == "all":
        validate_area(feature_id, targeting.get("area"))


def validate_area(feature_id, area):
    require_mapping(area, f"zone de {feature_id}")
    require_equal(area.get("shape"), "radius", f"Forme de zone de {feature_id}")
    distance = area.get("distance")
    require_mapping(distance, f"distance de {feature_id}")
    require_positive(distance.get("value"), f"distance de {feature_id}")
    require_equal(distance.get("unit"), "meter", f"Unité de {feature_id}")


def validate_operation(feature_id, operation):
    require_mapping(operation, f"opération de {feature_id}")
    validator = OPERATION_VALIDATORS.get(operation.get("type"))
    if validator is None:
        raise InvalidRequest(f"Opération inconnue pour {feature_id}.")
    if operation.get("target") not in OPERATION_TARGETS:
        raise InvalidRequest(f"Cible invalide pour {feature_id}.")
    validator(feature_id, operation)


def validate_formula(feature_id, formula):
    require_mapping(formula, f"formule de {feature_id}")
    validate_dice(feature_id, formula.get("dice"))
    if not isinstance(formula.get("terms", []), list):
        raise InvalidRequest(f"Termes invalides pour {feature_id}.")
    for term in formula.get("terms", []):
        validate_term(feature_id, term)


def validate_modifier(feature_id, operation):
    stat = operation.get("stat")
    if stat not in {"defense.all", "defense.physical", "defense.elemental", "defense.spiritual",
                    "movement.speed", "initiative", "saving_throw.all"}:
        raise InvalidRequest(f"Statistique invalide pour {feature_id}.")
    if not isinstance(operation.get("value"), int) or isinstance(operation["value"], bool):
        raise InvalidRequest(f"Modificateur invalide pour {feature_id}.")
    validate_optional_duration(feature_id, operation.get("duration"))
    validate_condition(feature_id, operation.get("condition"))


def validate_attack(feature_id, operation):
    require_equal(operation.get("delivery"), "natural_weapon", f"Arme de {feature_id}")
    require_equal(operation.get("damage_type"), "physical", f"Dégâts de {feature_id}")
    validate_formula(feature_id, operation.get("damage"))


def validate_movement(feature_id, operation):
    require_equal(operation.get("mode"), "flight", f"Déplacement de {feature_id}")
    distance = operation.get("speed")
    require_mapping(distance, f"vitesse de {feature_id}")
    require_positive(distance.get("value"), f"vitesse de {feature_id}")
    require_equal(distance.get("unit"), "meter", f"Unité de {feature_id}")


def validate_health_floor(feature_id, operation):
    require_positive(operation.get("value"), f"seuil de PV de {feature_id}")


def validate_bonus_damage(feature_id, operation):
    damage_type = operation.get("damage_type")
    if damage_type not in {"inherited", "physical", "elemental", "spiritual", "poison",
                           "fire", "ice", "lightning", "light", "dark", "magic"}:
        raise InvalidRequest(f"Type de dégâts invalide pour {feature_id}.")
    validate_formula(feature_id, operation.get("value"))
    validate_optional_duration(feature_id, operation.get("duration"))
    validate_frequency(feature_id, operation.get("frequency"))
    validate_condition(feature_id, operation.get("condition"))


def validate_frequency(feature_id, frequency):
    if frequency not in {"once_per_turn", "each_attack", "first_attack", "next_attack"}:
        raise InvalidRequest(f"Fréquence invalide pour {feature_id}.")


def validate_regeneration(feature_id, operation):
    validate_formula(feature_id, operation.get("value"))
    validate_frequency(feature_id, operation.get("frequency"))
    validate_optional_duration(feature_id, operation.get("duration"))
    validate_trigger(feature_id, operation.get("trigger"))


def validate_trigger(feature_id, trigger):
    if trigger is None:
        return
    require_mapping(trigger, f"déclencheur de {feature_id}")
    trigger_type = trigger.get("type")
    if trigger_type not in {"health_below_fraction", "state_active", "health_zero"}:
        raise InvalidRequest(f"Déclencheur invalide pour {feature_id}.")
    validate_trigger_value(feature_id, trigger_type, trigger)


def validate_trigger_value(feature_id, trigger_type, trigger):
    if trigger_type == "health_below_fraction":
        require_positive(trigger.get("numerator"), f"numérateur de {feature_id}")
        require_positive(trigger.get("denominator"), f"dénominateur de {feature_id}")
    if trigger_type == "state_active" and trigger.get("state") != "rooted":
        raise InvalidRequest(f"État déclencheur invalide pour {feature_id}.")


def validate_immunity(feature_id, operation):
    if operation.get("status") not in {"fear", "ordinary_disease", "ordinary_poison"}:
        raise InvalidRequest(f"Immunité invalide pour {feature_id}.")
    validate_optional_duration(feature_id, operation.get("duration"))


def validate_temporary_health(feature_id, operation):
    validate_formula(feature_id, operation.get("value"))
    validate_optional_duration(feature_id, operation.get("duration"))


def validate_damage(feature_id, operation):
    validate_damage_type(feature_id, operation.get("damage_type"))
    validate_formula(feature_id, operation.get("value"))
    if operation.get("timing", "immediate") not in {"immediate", "next_turn"}:
        raise InvalidRequest(f"Déclenchement des dégâts invalide pour {feature_id}.")
    validate_optional_duration(feature_id, operation.get("duration"))
    validate_damage_triggers(feature_id, operation.get("triggers"))


def validate_damage_type(feature_id, damage_type):
    known = {"physical", "elemental", "spiritual", "poison", "fire", "ice",
             "lightning", "light", "dark", "magic", "untyped"}
    if damage_type not in known:
        raise InvalidRequest(f"Type de dégâts invalide pour {feature_id}.")


def validate_extra_attack(feature_id, operation):
    require_positive(operation.get("count"), f"attaques supplémentaires de {feature_id}")
    validate_optional_duration(feature_id, operation.get("duration"))


def validate_ignore_defense(feature_id, operation):
    if operation.get("defense") not in {"physical", "elemental", "spiritual"}:
        raise InvalidRequest(f"Défense ignorée invalide pour {feature_id}.")
    validate_penetration(feature_id, operation)
    validate_condition(feature_id, operation.get("condition"))
    if operation.get("frequency"):
        validate_frequency(feature_id, operation["frequency"])


def validate_choice(feature_id, operation):
    options = operation.get("options")
    if not isinstance(options, list) or len(options) < 2:
        raise InvalidRequest(f"Options invalides pour {feature_id}.")
    for option in options:
        require_mapping(option, f"option de {feature_id}")
        if not option.get("id") or not option.get("operations"):
            raise InvalidRequest(f"Option incomplète pour {feature_id}.")
        if option.get("targeting"):
            validate_targeting(feature_id, option["targeting"])
        for child in option["operations"]:
            validate_operation(feature_id, child)


def validate_multiplier(feature_id, operation):
    if operation.get("stat") != "movement.speed":
        raise InvalidRequest(f"Statistique multiplicative invalide pour {feature_id}.")
    if operation.get("factor") not in {0.5, 2}:
        raise InvalidRequest(f"Facteur invalide pour {feature_id}.")
    validate_optional_duration(feature_id, operation.get("duration"))


def validate_damage_triggers(feature_id, triggers):
    if triggers is None:
        return
    known = {"enter_area", "start_turn", "each_turn"}
    if not isinstance(triggers, list) or not set(triggers) <= known:
        raise InvalidRequest(f"Déclencheurs de dégâts invalides pour {feature_id}.")


def validate_penetration(feature_id, operation):
    if "value" in operation:
        require_positive(operation["value"], f"pénétration de {feature_id}")
    elif operation.get("factor") != 0.5:
        raise InvalidRequest(f"Pénétration invalide pour {feature_id}.")


def validate_negation(feature_id, operation):
    roll = operation.get("roll")
    require_mapping(roll, f"jet d'annulation de {feature_id}")
    validate_dice(feature_id, roll.get("dice"))
    if roll.get("success_on") != [5, 6]:
        raise InvalidRequest(f"Seuil d'annulation invalide pour {feature_id}.")


def validate_forced_movement(feature_id, operation):
    require_equal(operation.get("direction"), "away", f"Direction de {feature_id}")
    distance = operation.get("distance")
    require_mapping(distance, f"distance de {feature_id}")
    require_positive(distance.get("value"), f"distance de {feature_id}")
    require_equal(distance.get("unit"), "meter", f"Unité de {feature_id}")


def validate_condition(feature_id, condition):
    if condition is None:
        return
    require_mapping(condition, f"condition de {feature_id}")
    known = {"damage_type", "weapon_tag", "chosen_weapon_family", "any"}
    if condition.get("type") not in known:
        raise InvalidRequest(f"Condition invalide pour {feature_id}.")


def validate_optional_duration(feature_id, duration):
    if duration is None:
        return
    require_mapping(duration, f"durée de {feature_id}")
    require_positive(duration.get("value"), f"durée de {feature_id}")
    require_equal(duration.get("unit"), "turn", f"Unité de durée de {feature_id}")


def validate_dice(feature_id, dice):
    require_mapping(dice, f"dés de {feature_id}")
    require_positive(dice.get("count"), f"nombre de dés de {feature_id}")
    require_positive(dice.get("sides"), f"faces de dés de {feature_id}")


def validate_term(feature_id, term):
    require_mapping(term, f"terme de {feature_id}")
    require_equal(term.get("type"), "ability_modifier", f"Terme de {feature_id}")
    if term.get("ability") not in {
        "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"
    }:
        raise InvalidRequest(f"Caractéristique invalide pour {feature_id}.")


def require_mapping(value, label):
    if not isinstance(value, dict):
        raise InvalidRequest(f"« {label} » doit être un objet.")


def require_positive(value, label):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidRequest(f"Valeur invalide pour {label}.")


def require_equal(value, expected, label):
    if value != expected:
        raise InvalidRequest(f"{label} invalide : {value!r}.")

from dnd_manager.shared.errors import InvalidRequest


EXECUTION_MODES = {"manual", "activated", "triggered", "permanent"}
ACTION_COSTS = {"action", "bonus_action", "reaction", "free", "none"}
TRIGGER_EVENTS = {
    "ally.targeted", "source.damaged", "target.damaged", "source.health_below_half",
    "source.health_zero", "turn.start", "attack.hit", "attack.missed", "combat.start",
}
ACTIVATION_LIMITS = {"once_per_turn", "once_per_round", "once_per_combat", "first_turn", "at_will"}
VALUE_REFERENCES = {
    "defense.all", "defense.physical", "defense.elemental", "defense.spiritual", "movement.walk",
    "initiative.bonus", "saving_throw.strength", "saving_throw.dexterity",
    "saving_throw.constitution", "saving_throw.intelligence", "saving_throw.wisdom",
    "saving_throw.charisma", "saving_throw.all", "health.current", "attack.damage",
}
TARGET_REFERENCES = {
    "source", "target.primary", "target.all", "target.allies", "target.enemies",
    "trigger.source", "trigger.target", "area.entities", "summon.created",
}
OPERATION_TYPES = {
    "damage", "heal", "health_cost", "health_floor", "temporary_health",
    "modify_attack_damage", "modify_value", "apply_status", "remove_status",
    "reduce_damage", "grant_immunity", "ignore_defense", "reflect_damage",
    "move", "extra_attack", "manual_effect",
}
OPERATION_MODES = {
    "add", "subtract", "set", "minimum", "maximum", "override", "multiply",
    "grant_advantage", "grant_disadvantage",
}


def capability_values(form, path_key):
    execution_mode = choice(form, "execution_mode", EXECUTION_MODES)
    values = {
        "path_key": path_key,
        "name": required_text(form, "name", "Le nom de la capacité est obligatoire."),
        "execution_mode": execution_mode,
        "action_cost": ("none" if execution_mode == "permanent"
                        else choice(form, "action_cost", ACTION_COSTS)),
        "trigger_event": optional_choice(form, "trigger_event", TRIGGER_EVENTS),
        "activation_limit": optional_choice(form, "activation_limit", ACTIVATION_LIMITS),
        "uses_maximum": optional_positive_integer(form.get("uses_maximum")),
        "recharge": optional_text(form, "recharge"),
        "operations": operations_from_form(form),
    }
    if not values["operations"]:
        raise InvalidRequest("Ajoute au moins un effet à la capacité.")
    validate_capability_consistency(values)
    values.update(inferred_targeting(values["operations"]))
    return values


def validate_capability_consistency(values):
    if values["execution_mode"] == "triggered" and not values["trigger_event"]:
        raise InvalidRequest("Choisis le déclencheur de cette capacité.")
    if values["execution_mode"] == "permanent":
        values["action_cost"] = "none"
        values["trigger_event"] = None
        values["activation_limit"] = None
        values["uses_maximum"] = None
        values["recharge"] = None
    if values["activation_limit"] == "at_will":
        values["uses_maximum"] = None
        values["recharge"] = None
    elif values["uses_maximum"] and not values["recharge"]:
        raise InvalidRequest("Choisis quand les utilisations sont récupérées.")
    elif not values["uses_maximum"]:
        values["recharge"] = None
    for index, operation in enumerate(values["operations"], 1):
        validate_operation_consistency(operation, index)


def validate_operation_consistency(operation, index):
    operation_type = operation["operation_type"]
    if operation_type == "manual_effect" and not operation["description"]:
        raise InvalidRequest(f"Décris la règle particulière de l’effet {index}.")
    needs_value = {"damage", "heal", "health_cost", "health_floor", "temporary_health",
                   "modify_attack_damage", "reduce_damage", "reflect_damage", "extra_attack"}
    if operation_type in needs_value and not any(
            operation[key] is not None for key in ("fixed_value", "dice_count")):
        raise InvalidRequest(f"Indique la valeur de l’effet {index}.")
    hostile = operation["target_ref"] in {"target.enemies"}
    beneficial = operation_type in {"heal", "temporary_health", "modify_attack_damage",
                                    "extra_attack", "grant_immunity"}
    if operation_type == "modify_value":
        beneficial = operation["operation_mode"] in {"add", "multiply", "grant_advantage"}
    if hostile and beneficial:
        raise InvalidRequest(
            f"L’effet {index} renforce les ennemis. Choisis une autre cible ou une modification négative."
        )


def operations_from_form(form):
    operations = []
    for index in range(nonnegative_integer(form.get("operation_count", 0))):
        prefix = f"operation_{index}_"
        operation_type = form.get(prefix + "type", "")
        if not operation_type:
            continue
        if operation_type not in OPERATION_TYPES:
            raise InvalidRequest(f"Type d’effet inconnu à l’opération {index + 1}.")
        target_ref = form.get(prefix + "target_ref", "")
        if target_ref not in TARGET_REFERENCES:
            raise InvalidRequest(f"Cible invalide à l’opération {index + 1}.")
        operations.append({
            "operation_type": operation_type, "target_ref": target_ref,
            "value_mode": form.get(prefix + "value_mode") or None,
            "fixed_value": optional_number(form.get(prefix + "fixed_value")),
            "dice_count": optional_positive_integer(form.get(prefix + "dice_count")),
            "dice_sides": optional_positive_integer(form.get(prefix + "dice_sides")),
            "resource_ref": optional_text(form, prefix + "resource_ref"),
            "value_ref": optional_choice(form, prefix + "value_ref", VALUE_REFERENCES),
            "damage_type": optional_text(form, prefix + "damage_type"),
            "status_ref": optional_text(form, prefix + "status_ref"),
            "operation_mode": optional_choice(form, prefix + "operation_mode", OPERATION_MODES),
            "distance_value": optional_number(form.get(prefix + "distance_value")),
            "distance_unit": "meter" if operation_type == "move" else None,
            "duration_value": optional_positive_integer(form.get(prefix + "duration_value")),
            "duration_unit": optional_text(form, prefix + "duration_unit"),
            "expiration": optional_text(form, prefix + "expiration"),
            "frequency": optional_text(form, prefix + "frequency"),
            "condition_type": optional_text(form, prefix + "condition_type"),
            "description": form.get(prefix + "description", "").strip(),
        })
        if operation_type in {"apply_status", "remove_status", "grant_immunity"}:
            if not operations[-1]["status_ref"]:
                raise InvalidRequest(f"Choisis un état à l’effet {index + 1}.")
        if operation_type == "modify_value":
            validate_value_change(operations[-1], index)
    return operations


def validate_value_change(operation, index):
    if not operation["value_ref"]:
        raise InvalidRequest(f"Choisis la statistique à l’effet {index + 1}.")
    mode = operation["operation_mode"] or "add"
    value = operation["fixed_value"]
    if mode not in {"grant_advantage", "grant_disadvantage"} and value is None:
        raise InvalidRequest(f"Indique la valeur de l’effet {index + 1}.")
    if mode in {"add", "subtract"} and value is not None and value <= 0:
        raise InvalidRequest(
            f"Utilise une valeur positive avec Ajouter ou Retirer à l’effet {index + 1}."
        )


def inferred_targeting(operations):
    references = {item["target_ref"] for item in operations}
    area = "area.entities" in references
    selected = any(reference.startswith("target.") for reference in references)
    only_primary = selected and references <= {"source", "target.primary"}
    return {
        "selection_mode": "area" if area else "manual" if selected else "none",
        "minimum_targets": 1 if selected else 0,
        "maximum_targets": 1 if only_primary else None,
        "range_value": None, "allegiance": "any", "entity_type": "creature",
        "allow_self": False, "requires_visibility": True,
        "area_shape": None, "area_size": None,
    }


def choice(form, name, choices):
    value = form.get(name, "")
    if value not in choices:
        raise InvalidRequest(f"Valeur invalide pour {name}.")
    return value


def optional_choice(form, name, choices):
    value = form.get(name, "")
    if not value:
        return None
    if value not in choices:
        raise InvalidRequest(f"Valeur invalide pour {name}.")
    return value


def required_text(form, name, message):
    value = form.get(name, "").strip()
    if not value:
        raise InvalidRequest(message)
    return value


def optional_text(form, name):
    return form.get(name, "").strip() or None


def optional_positive_integer(value):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidRequest("Une valeur entière est attendue.") from error
    if parsed <= 0:
        raise InvalidRequest("La valeur doit être supérieure à zéro.")
    return parsed


def nonnegative_integer(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidRequest("Une valeur entière est attendue.") from error
    if parsed < 0:
        raise InvalidRequest("La valeur ne peut pas être négative.")
    return parsed


def optional_number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise InvalidRequest("Une valeur numérique est attendue.") from error

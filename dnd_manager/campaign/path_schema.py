import re
import unicodedata

from dnd_manager.shared.errors import InvalidRequest


SUPPORT_LEVELS = {"full", "partial", "manual"}
SELECTORS = {"self", "single", "multiple", "all"}
ALLEGIANCES = {"ally", "enemy", "neutral"}
OPERATION_TYPES = {
    "modify_stat", "modify_resource", "damage", "define_attack",
    "modify_protection", "apply_status", "move", "extra_attack",
    "force_critical", "cancel_event", "trigger_action", "summon",
    "use_ability", "reveal", "choice", "custom_ability",
}
RECHARGES = {"short_rest", "long_rest"}


def slug(value):
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")


def capability_id(origin, path_name, rank, mode):
    return f"path.{slug(origin)}.{slug(path_name)}.rank-{rank}.{mode}"


def validate_capability(capability, expected_rank=None):
    if not isinstance(capability, dict):
        raise InvalidRequest("La capacité doit être un objet JSON.")
    identifier = capability.get("id", "")
    pattern = r"^path\.[a-z0-9-]+\.[a-z0-9-]+\.rank-(\d+)\.(active|passive)$"
    match = re.fullmatch(pattern, identifier)
    if match is None:
        raise InvalidRequest(f"Identifiant de capacité invalide : {identifier or 'absent'}.")
    if expected_rank is not None and int(match.group(1)) != expected_rank:
        raise InvalidRequest(f"Le rang de {identifier} est incohérent.")
    if capability.get("support") not in SUPPORT_LEVELS:
        raise InvalidRequest(f"Niveau de support invalide pour {identifier}.")
    validate_targeting(identifier, capability.get("targeting"))
    operations = capability.get("operations")
    if not isinstance(operations, list) or not operations:
        raise InvalidRequest(f"Ajoute au moins une opération à {identifier}.")
    for operation in operations:
        validate_operation(identifier, operation)
    validate_uses(identifier, capability.get("uses"))
    return capability


def validate_targeting(identifier, targeting):
    if not isinstance(targeting, dict) or targeting.get("selector") not in SELECTORS:
        raise InvalidRequest(f"Ciblage invalide pour {identifier}.")
    allegiance = targeting.get("allegiance", [])
    if not isinstance(allegiance, list) or not set(allegiance) <= ALLEGIANCES:
        raise InvalidRequest(f"Camp ciblé invalide pour {identifier}.")
    if targeting["selector"] == "self" and (allegiance or targeting.get("area")):
        raise InvalidRequest("Une capacité personnelle ne peut pas définir de camp ou de zone.")


def validate_operation(identifier, operation):
    if not isinstance(operation, dict) or operation.get("type") not in OPERATION_TYPES:
        raise InvalidRequest(f"Opération inconnue pour {identifier}.")
    if operation.get("target", "selected") not in {"selected", "self"}:
        raise InvalidRequest(f"Cible d’opération invalide pour {identifier}.")
    operation_type = operation["type"]
    required = {
        "modify_stat": ("stat", "operation", "value"),
        "modify_resource": ("resource", "operation", "value"),
        "damage": ("damage_type", "value"),
        "apply_status": ("status",),
        "move": ("distance",),
        "choice": ("options",),
        "custom_ability": ("description",),
    }.get(operation_type, ())
    missing = [field for field in required if field not in operation]
    if missing:
        raise InvalidRequest(f"Paramètres manquants pour {operation_type} : {', '.join(missing)}.")
    validate_duration(identifier, operation.get("duration"))
    if operation_type == "choice":
        options = operation["options"]
        if not isinstance(options, list) or len(options) < 2:
            raise InvalidRequest(f"Un choix doit proposer au moins deux options ({identifier}).")


def validate_duration(identifier, duration):
    if duration is None:
        return
    if (not isinstance(duration, dict) or duration.get("unit") not in {"turn", "round"}
            or not positive_integer(duration.get("value"))):
        raise InvalidRequest(f"Durée invalide pour {identifier}.")


def validate_uses(identifier, uses):
    if uses is None:
        return
    if (not isinstance(uses, dict) or not positive_integer(uses.get("maximum"))
            or uses.get("recharge") not in RECHARGES):
        raise InvalidRequest(f"Utilisations invalides pour {identifier}.")


def positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def describe_capability(capability):
    return " ".join(describe_capability_items(capability))


def describe_capability_items(capability):
    targets = {
        "self": "Le personnage", "single": "La cible", "multiple": "Les cibles",
        "all": "Les cibles dans la zone",
    }
    targeting = capability.get("targeting", {})
    subject = targets.get(targeting.get("selector"), "La cible")
    allegiance = targeting.get("allegiance", [])
    if allegiance:
        labels = {"ally": "alliée", "enemy": "ennemie", "neutral": "neutre"}
        subject += f" {labels.get(allegiance[0], allegiance[0])}"
    operations = capability.get("operations", [])
    effects, consumed = describe_targeting(targeting, operations), set()
    for index, operation in enumerate(operations):
        if index in consumed:
            continue
        operation_subject = operation_subject_label(operation, subject)
        if operation.get("type") == "custom_ability":
            description = operation.get("description", "").strip()
            if description:
                effects.append(description)
            continue
        defense_group = matching_defense_group(operations, index)
        if defense_group:
            consumed.update(defense_group)
            effects.append(f"{operation_subject} {describe_all_defenses(operation, operation_subject)}.")
            continue
        description = describe_operation(operation)
        if operation_subject.startswith("Les "):
            description = pluralize_description(description)
        effects.append(f"{operation_subject} {description}.")
    return effects


def describe_targeting(targeting, operations):
    """Rend visibles les portées qui seraient sinon seulement stockées par l’éditeur."""
    selector = targeting.get("selector")
    allegiance = targeting.get("allegiance", [])
    label = {"ally": "alliées", "enemy": "ennemies", "neutral": "neutres"}.get(
        allegiance[0] if allegiance else None, ""
    )
    if selector == "multiple" and targeting.get("range"):
        distance = targeting["range"]
        if targeting_distance_is_already_described(distance, operations):
            return []
        unit = "m" if distance.get("unit") == "meter" else distance.get("unit", "m")
        qualifier = f" {label}" if label else ""
        return [
            f"Choisissez une ou plusieurs cibles{qualifier} situées à "
            f"{distance.get('value'):g} {unit} ou moins."
        ]
    if selector == "all" and targeting.get("area"):
        distance = targeting["area"].get("distance", {})
        if targeting_distance_is_already_described(distance, operations):
            return []
        unit = "m" if distance.get("unit") == "meter" else distance.get("unit", "m")
        qualifier = f" {label}" if label else ""
        return [
            f"La zone affecte toutes les cibles{qualifier} situées dans un rayon de "
            f"{distance.get('value'):g} {unit}."
        ]
    return []


def targeting_distance_is_already_described(distance, operations):
    value = distance.get("value")
    if value is None:
        return False
    rendered = f"{value:g} m"
    return any(
        operation.get("type") == "custom_ability"
        and rendered in operation.get("description", "")
        for operation in operations
    )


def operation_subject_label(operation, fallback):
    return {
        "source": "Le personnage", "target.primary": "La cible principale",
        "target.all": "Les cibles", "target.allies": "Les cibles alliées",
        "target.enemies": "Les cibles ennemies", "trigger.source": "L’auteur du déclenchement",
        "trigger.target": "La cible du déclenchement",
        "area.entities": "Les créatures dans la zone",
        "summon.created": "La créature invoquée",
    }.get(operation.get("target_ref"),
          "Le personnage" if operation.get("target") == "self" else fallback)


def pluralize_description(description):
    """Accorde le premier verbe des descriptions générées dont le sujet est pluriel."""
    replacements = {
        "subit ": "subissent ", "ajoute ": "ajoutent ", "récupère ": "récupèrent ",
        "perd ": "perdent ", "fixe ": "fixent ", "régénère ": "régénèrent ",
        "augmente ": "augmentent ", "réduit ": "réduisent ", "multiplie ": "multiplient ",
        "modifie ": "modifient ", "reçoit ": "reçoivent ", "se déplace ": "se déplacent ",
        "est repoussée ": "sont repoussées ", "peut voler ": "peuvent voler ",
        "obtient ": "obtiennent ", "gagne ": "gagnent ", "choisit ": "choisissent ",
        "doit choisir ": "doivent choisir ", "reste ": "restent ", "est immunisé ": "sont immunisées ",
        "ignore ": "ignorent ", "bénéficie ": "bénéficient ",
    }
    for singular, plural in replacements.items():
        if description.startswith(singular):
            result = plural + description[len(singular):]
            return (result.replace(" sa ", " leur ")
                    .replace(" son ", " leur ")
                    .replace(" ses ", " leurs "))
    return description


def matching_defense_group(operations, start):
    operation = operations[start]
    defenses = {"defense.physical", "defense.elemental", "defense.spiritual"}
    if operation.get("type") != "modify_stat" or operation.get("stat") not in defenses:
        return None
    comparable = {key: operation.get(key) for key in
                  ("type", "target", "operation", "value", "duration", "condition")}
    matches = [index for index, candidate in enumerate(operations)
               if candidate.get("stat") in defenses
               and {key: candidate.get(key) for key in comparable} == comparable]
    return matches if {operations[index]["stat"] for index in matches} == defenses else None


def describe_all_defenses(operation, subject):
    value = operation.get("value", 0)
    plural = subject.startswith("Les ")
    possessive = "leurs" if plural else "ses"
    if operation.get("operation") == "subtract" or value < 0:
        verb, rendered = ("réduisent" if plural else "réduit"), f"{abs(value):g}"
    else:
        verb, rendered = ("augmentent" if plural else "augmente"), f"+{value:g}"
    return (f"{verb} toutes {possessive} Défenses de {rendered}{describe_duration(operation)}"
            f"{describe_condition(operation)}")


def describe_operation(operation):
    operation_type = operation.get("type")
    if operation_type == "damage":
        value = describe_value(operation.get("value"))
        damage_type = damage_type_label(operation.get("damage_type"))
        if operation.get("mode") == "attach":
            once_per_turn = operation.get("frequency") == "once_per_turn"
            recipient = ("à ses sorts" if operation.get("applies_to") == "spell" else
                         "à une attaque" if once_per_turn else "à sa prochaine attaque")
            frequency = " une fois par tour" if once_per_turn else ""
            return f"ajoute {value} dégâts{damage_type} {recipient}{frequency}{describe_duration(operation)}"
        if operation.get("frequency") == "once_per_turn":
            return (f"subit {value} dégâts{damage_type} au début de chacun de ses tours"
                    f"{describe_duration(operation)}")
        return f"subit {value} dégâts{damage_type}{describe_duration(operation)}"
    if operation_type == "modify_resource":
        if operation.get("operation") == "set_minimum":
            minimum = describe_value(operation.get("value")).removeprefix("+")
            return (f"reste à au moins {minimum} PV "
                    "au lieu de tomber à 0 PV")
        regeneration = (operation.get("frequency") == "once_per_turn"
                        and operation.get("operation") == "add")
        temporary = operation.get("resource") == "temporary_health"
        verb = ("gagne" if temporary else "régénère" if regeneration else
                {"add": "récupère", "subtract": "perd", "set": "fixe"}.get(
                    operation.get("operation"), "modifie"))
        resource = "PV temporaires" if temporary else "PV"
        frequency = " par tour" if operation.get("frequency") == "once_per_turn" else ""
        trigger = describe_trigger(operation.get("trigger"))
        return (f"{verb} {describe_value(operation.get('value'))} {resource}{frequency}"
                f"{describe_duration(operation)}{trigger}")
    if operation_type == "modify_stat":
        value = operation.get("value", 0)
        if isinstance(value, dict):
            rendered = describe_value(value)
        elif operation.get("operation") == "subtract" or value < 0:
            rendered = f"{abs(value):g}"
        else:
            rendered = f"+{value:g}" if operation.get("operation") == "add" else f"{value:g}"
        stat = stat_label(operation.get("stat"))
        if operation.get("stat") in {"movement.speed", "movement.walk"}:
            rendered += " m"
        verb = {"add": "augmente", "subtract": "réduit", "set": "fixe",
                "multiply": "multiplie"}.get(operation.get("operation"), "modifie")
        return (f"{verb} {stat} de {rendered}{describe_duration(operation)}"
                f"{describe_condition(operation)}")
    if operation_type == "modify_protection":
        if operation.get("status"):
            statuses = {"fear": "la peur", "ordinary_disease": "les maladies ordinaires",
                        "ordinary_poison": "les poisons ordinaires"}
            status = statuses.get(operation["status"], operation["status"])
            return f"est immunisé contre {status}{describe_duration(operation)}"
        if operation.get("defense"):
            defense = {"physical": "physique", "elemental": "élémentaire",
                       "spiritual": "spirituelle"}.get(
                           operation["defense"], operation["defense"],
                       )
            value = operation.get("value")
            penetration = (f"{value} point{'s' if value != 1 else ''} de "
                           if isinstance(value, int) else "la moitié de la ")
            return f"ignore {penetration}Défense {defense}{describe_condition(operation)}"
        if isinstance(operation.get("value"), dict):
            reflection = " et renvoie les dégâts annulés" if operation.get("reflect") else ""
            return (f"réduit les dégâts reçus de {describe_value(operation.get('value'))}"
                    f"{reflection}")
        return "bénéficie de la protection indiquée" + describe_duration(operation)
    if operation_type == "apply_status":
        return f"reçoit l’état {operation.get('status', 'non défini')}{describe_duration(operation)}"
    if operation_type == "move":
        distance = operation.get("distance", {})
        value = distance.get("value", 0)
        rendered_value = f"{value:g}" if isinstance(value, (int, float)) else value
        unit = "m" if distance.get("unit") == "meter" else distance.get("unit", "m")
        if operation.get("direction") == "away":
            return f"est repoussée de {rendered_value} {unit}"
        if operation.get("mode") == "flight":
            return f"peut voler sur {rendered_value} {unit}"
        return f"se déplace de {rendered_value} {unit}"
    if operation_type == "define_attack" and operation.get("damage"):
        damage_type = damage_type_label(operation.get("damage_type"))
        return (f"obtient une attaque naturelle infligeant "
                f"{describe_value(operation['damage'])} dégâts{damage_type}")
    if operation_type == "extra_attack":
        count = operation.get("count", 1)
        return f"gagne {count} attaque{'s' if count > 1 else ''} supplémentaire{'s' if count > 1 else ''}{describe_duration(operation)}"
    if operation_type == "choice":
        options = operation.get("options") or []
        rendered = []
        for option in options:
            if isinstance(option, str) and option.strip():
                rendered.append(option.strip())
            elif isinstance(option, dict):
                label = (option.get("label") or option.get("description") or "").strip()
                if label:
                    rendered.append(label)
        if rendered:
            return "choisit entre : " + " ; ".join(rendered)
        return "doit choisir un effet (options manquantes)"
    if operation_type == "custom_ability":
        return operation.get("description", "").strip()
    labels = {
        "modify_protection": "modifie une protection", "define_attack": "obtient une attaque",
        "force_critical": "réussit un coup critique", "cancel_event": "annule un événement",
        "trigger_action": "déclenche une action", "summon": "invoque une créature",
        "use_ability": "utilise une capacité", "reveal": "révèle une information",
        "choice": "choisit entre plusieurs effets",
    }
    return labels.get(operation_type, "applique un effet") + describe_duration(operation)


def describe_value(value):
    if not isinstance(value, dict):
        return str(value or 0)
    dice = value.get("dice", [])
    if isinstance(dice, dict):
        dice = [dice]
    parts = [f"{die['count']}d{die['sides']}" for die in dice if die.get("count")]
    ability_labels = {"strength": "Force", "dexterity": "Dextérité",
                      "constitution": "Constitution", "intelligence": "Intelligence",
                      "wisdom": "Sagesse", "charisma": "Charisme"}
    parts.extend(ability_modifier_label(
        ability_labels.get(term.get("ability"), term.get("ability", "")),
    ) for term in value.get("terms", []) if term.get("type") == "ability_modifier")
    if value.get("constant"):
        parts.append(f"{value['constant']:+d}")
    return " + ".join(parts).replace("+ +", "+ ") or "0"


def ability_modifier_label(ability):
    article = "d’" if ability == "Intelligence" else "de "
    return f"modificateur {article}{ability}"


def describe_duration(operation):
    duration = operation.get("duration")
    if not duration:
        return ""
    value = duration.get("value")
    if duration.get("unit") == "turn":
        unit = "tour de l’utilisateur" if value == 1 else "tours de l’utilisateur"
    else:
        unit = "tour global" if value == 1 else "tours globaux"
    return f" pendant {value} {unit}"


def describe_trigger(trigger):
    if not trigger:
        return ""
    if trigger.get("type") == "health_below_fraction":
        numerator, denominator = trigger.get("numerator"), trigger.get("denominator")
        if (numerator, denominator) == (1, 2):
            return " lorsqu’il tombe sous la moitié de ses PV"
        return f" lorsqu’il tombe sous {numerator}/{denominator} de ses PV"
    labels = {"start_turn": " au début du tour", "enter_area": " en entrant dans la zone"}
    return labels.get(trigger.get("type"), "")


def describe_condition(operation):
    condition = operation.get("condition") or {}
    condition_type = condition.get("type")
    if condition_type == "weapon_tag":
        return " avec une arme gigantesque"
    if condition_type == "chosen_weapon_family":
        return " avec une famille d’armes choisie"
    if condition_type == "shield_equipped":
        return " avec un bouclier équipé"
    if condition_type == "incoming_attack":
        return " uniquement contre cette attaque"
    return ""


def stat_label(stat):
    return {
        "defense.all": "toutes ses Défenses",
        "defense.physical": "sa Défense physique",
        "defense.elemental": "sa Défense élémentaire",
        "defense.spiritual": "sa Défense spirituelle",
        "movement.speed": "sa vitesse de déplacement",
        "movement.walk": "sa vitesse de déplacement à pied",
        "initiative.bonus": "son bonus d’Initiative",
        "initiative": "son Initiative", "saving_throw.all": "ses jets de sauvegarde",
        "intelligence.arcane": "ses tests d’Intelligence liés aux Arcanes",
    }.get(stat, str(stat or "une statistique"))


def damage_type_label(damage_type):
    return {
        "physical": " physiques", "elemental": " élémentaires",
        "spiritual": " spirituels", "fire": " de feu", "ice": " de glace",
        "lightning": " de foudre", "light": " de lumière", "dark": " de Ténèbres",
        "magic": " magiques", "poison": " de poison", "untyped": "",
        "inherited": "",
    }.get(damage_type, f" ({damage_type})" if damage_type else "")


def legacy_capabilities(path_id, rank, engine_rules=None):
    capabilities = []
    for mode in ("active", "passive"):
        detail = rank.get(mode)
        if detail is None:
            continue
        identifier = f"{path_id}.rank-{rank['rank']}.{mode}"
        resolution = (engine_rules or {}).get(identifier)
        if resolution:
            capability = {"id": identifier, "support": resolution["support"],
                          "targeting": normalize_targeting(
                              resolution.get("targeting", {"selector": "self"})),
                          "operations": [normalize_operation(item)
                                         for item in resolution["operations"]]}
        else:
            capability = {"id": identifier, "support": "partial",
                          "targeting": {"selector": "self"},
                          "operations": [{"type": "custom_ability", "target": "self",
                                          "description": detail.get("effect", rank["name"])}]}
        uses = legacy_uses(detail)
        if uses:
            capability["uses"] = uses
        capabilities.append(capability)
    return capabilities


def normalize_operation(operation):
    item = dict(operation)
    if item.get("target") not in {"selected", "self"}:
        item["target"] = "selected"
    duration = item.get("duration")
    if isinstance(duration, dict) and duration.get("unit") in RECHARGES | {"rest"}:
        item["expires_on"] = ("long_rest" if duration["unit"] == "rest"
                              else duration["unit"])
        item.pop("duration")
    elif isinstance(duration, dict) and not positive_integer(duration.get("value")):
        item.pop("duration")
    old_type = item["type"]
    replacements = {
        "attack_profile": "define_attack", "grant_movement": "move",
        "bonus_movement": "move", "modify_movement": "move",
        "forced_movement": "move", "grant_immunity": "modify_protection",
        "ignore_defense": "modify_protection", "reduce_damage": "modify_protection",
        "auto_stabilize": "apply_status", "negate_attack": "cancel_event",
        "cancel_attack": "cancel_event", "cancel_spell": "cancel_event",
        "counter_attack": "trigger_action", "cast_spell": "use_ability",
        "copy_ability": "use_ability", "duplicate_spell": "use_ability",
        "analyze": "reveal", "detect_resource": "reveal",
        "bonus_ability": "custom_ability", "bonus": "modify_stat",
        "multiply_stat": "modify_stat", "set_health_floor": "modify_resource",
        "temporary_health": "modify_resource", "regeneration": "modify_resource",
    }
    if old_type == "heal":
        item.update(type="modify_resource", resource="health", operation="add")
    elif old_type == "bonus_damage":
        item.update(type="damage", mode="attach")
    else:
        item["type"] = replacements.get(old_type, old_type)
    if item["type"] == "modify_stat":
        item.setdefault("stat", "custom.unspecified")
        item.setdefault("operation", "multiply" if old_type == "multiply_stat" else "add")
        item.setdefault("value", item.get("amount", 0))
        if "factor" in item and "value" not in item:
            item["value"] = item["factor"]
    if item["type"] == "modify_resource":
        item.setdefault("resource", "temporary_health" if old_type == "temporary_health"
                        else "health")
        item.setdefault("operation", "set_minimum" if old_type == "set_health_floor" else "add")
        item.setdefault("value", item.get("value", 1))
    if item["type"] == "move" and "distance" not in item:
        item["distance"] = item.get("speed", {"value": 1, "unit": "meter"})
    if item["type"] == "apply_status":
        item.setdefault("status", "stable")
    if item["type"] == "custom_ability":
        item.setdefault("description", item.get("name", "Capacité manuelle à préciser"))
    if item["type"] == "damage":
        item.setdefault("damage_type", "untyped")
        item.setdefault("value", {"dice": [], "terms": [], "constant": 0})
    if item["type"] == "choice":
        item["options"] = [
            {**option, "operations": [normalize_operation(child)
                                      for child in option.get("operations", [])]}
            for option in item.get("options", [])
        ]
    return item


def normalize_targeting(targeting):
    item = dict(targeting)
    selector = item.get("selector", "self")
    if selector not in SELECTORS:
        item["selector"] = "all" if "all" in selector else "single"
    if item["selector"] == "self":
        item.pop("allegiance", None)
        item.pop("area", None)
    return item


def legacy_uses(detail):
    resource = detail.get("resource") or {}
    recoveries = resource.get("recovery", [])
    if resource.get("maximum") and recoveries:
        return {"maximum": resource["maximum"], "recharge": recoveries[-1]}
    return None

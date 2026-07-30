from dnd_manager.shared.errors import InvalidRequest

SUPPORTED_SCHEMA_VERSION = "2.0.0"


def validate_config(config):
    require_equal(config.get("schema_version"), SUPPORTED_SCHEMA_VERSION, "Version de schéma")
    require_mapping(config.get("ruleset"), "ruleset")
    require_mapping(config.get("definitions"), "definitions")
    validate_groups(config)
    validate_unique_ids(config)
    return config


def validate_groups(config):
    for name in ("classes", "races"):
        items = config.get(name)
        if not isinstance(items, list) or not items:
            raise InvalidRequest(f"La collection « {name} » est vide ou invalide.")
        for item in items:
            validate_item(item, name)


def validate_item(item, group):
    require_identifier(item, group)
    paths = item.get("paths")
    if not isinstance(paths, list) or not paths:
        raise InvalidRequest(f"{item['id']} doit déclarer au moins une voie.")
    for path in paths:
        validate_path(path)


def validate_path(path):
    require_identifier(path, "voie")
    validate_path_defenses(path)
    ranks = path.get("ranks")
    require_equal([rank.get("rank") for rank in ranks], [1, 2, 3, 4, 5],
                  f"Rangs de {path['id']}")
    for rank in ranks:
        require_identifier(rank, "capacité")
        validate_rank(rank)


def validate_path_defenses(path):
    defenses = path.get("defenses")
    if defenses is None:
        return
    require_mapping(defenses, f"défenses de {path['id']}")
    if set(defenses) != {"physical", "elemental", "spiritual"}:
        raise InvalidRequest(f"Défenses incomplètes pour {path['id']}.")
    if any(not isinstance(value, int) or isinstance(value, bool) for value in defenses.values()):
        raise InvalidRequest(f"Bonus de Défense invalide pour {path['id']}.")


def validate_rank(rank):
    if rank.get("active") is None and rank.get("passive") is None:
        raise InvalidRequest(f"{rank['id']} ne définit aucun effet.")
    for mode in ("active", "passive"):
        value = rank.get(mode)
        if value is not None:
            validate_automation(rank["id"], value)
            validate_resource(rank["id"], value.get("resource"))


def validate_resource(feature_id, resource):
    if resource is None:
        return
    require_mapping(resource, f"ressource de {feature_id}")
    recoveries = resource.get("recovery")
    if not isinstance(recoveries, list) or not recoveries:
        raise InvalidRequest(f"Récupération manquante pour {feature_id}.")
    if any(value not in {"short_rest", "long_rest"} for value in recoveries):
        raise InvalidRequest(f"Type de repos invalide pour {feature_id}.")


def validate_automation(feature_id, value):
    automation = value.get("automation")
    require_mapping(automation, f"automation de {feature_id}")
    if automation.get("level") not in {"manual", "partial", "full"}:
        raise InvalidRequest(f"Niveau d’automatisation invalide pour {feature_id}.")
    if not isinstance(automation.get("effects"), list):
        raise InvalidRequest(f"Les effets de {feature_id} doivent former une liste.")
    validate_effects(feature_id, automation["effects"])


def validate_effects(feature_id, effects):
    for effect in effects:
        validate_effect(feature_id, effect)


def validate_effect(feature_id, effect):
    require_mapping(effect, f"effet de {feature_id}")
    validator = effect_validator(effect.get("type"))
    if validator is None:
        raise InvalidRequest(f"Type d’effet invalide pour {feature_id}.")
    require_equal(effect.get("target"), "self", f"Cible de {feature_id}")
    validator(feature_id, effect)


def effect_validator(effect_type):
    return {"deal_damage": validate_value_effect, "heal": validate_value_effect}.get(effect_type)


def validate_value_effect(feature_id, effect):
    validate_formula(feature_id, effect.get("value"))


def validate_formula(feature_id, formula):
    require_mapping(formula, f"formule de {feature_id}")
    dice = formula.get("dice")
    require_mapping(dice, f"dés de {feature_id}")
    if not positive_integer(dice.get("count")) or not positive_integer(dice.get("sides")):
        raise InvalidRequest(f"Dés invalides pour {feature_id}.")


def positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_unique_ids(config):
    identifiers = list(all_identifiers(config))
    if len(identifiers) != len(set(identifiers)):
        raise InvalidRequest("Les identifiants du fichier de jeu ne sont pas uniques.")


def all_identifiers(config):
    for group in ("classes", "races"):
        for item in config[group]:
            yield item["id"]
            for path in item["paths"]:
                yield path["id"]
                yield from (rank["id"] for rank in path["ranks"])


def require_identifier(value, label):
    identifier = value.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise InvalidRequest(f"Identifiant manquant pour {label}.")


def require_mapping(value, label):
    if not isinstance(value, dict):
        raise InvalidRequest(f"« {label} » doit être un objet.")


def require_equal(value, expected, label):
    if value != expected:
        raise InvalidRequest(f"{label} invalide : {value!r}.")

import json

from dnd_manager.campaign.path_schema import describe_capability, describe_capability_items


EXECUTABLE_OPERATIONS = {"damage", "heal", "health_cost"}
EXECUTION_MODE_LABELS = {
    "manual": "Manuelle", "activated": "Activée par le joueur",
    "triggered": "Déclenchée automatiquement", "permanent": "Permanente",
}
ACTION_COST_LABELS = {
    "action": "Action", "bonus_action": "Action bonus", "reaction": "Réaction",
    "free": "Action libre", "none": "Aucune action",
}
RECHARGE_LABELS = {"short_rest": "repos court", "long_rest": "repos long"}


def migrate_existing_capabilities(database):
    """Copie une seule fois le catalogue actuel vers le modèle rang/capacité."""
    definitions = database.execute("SELECT id, stable_key FROM path_definition").fetchall()
    for definition in definitions:
        if database.execute(
            "SELECT 1 FROM path_rank WHERE path_definition_id = ? LIMIT 1", (definition["id"],)
        ).fetchone():
            continue
        migrate_definition(database, definition)


def migrate_definition(database, definition):
    rows = database.execute(
        "SELECT * FROM path_rank_definition WHERE path_definition_id = ? ORDER BY rank, id",
        (definition["id"],),
    ).fetchall()
    ranks = {}
    for row in rows:
        rank_id = ranks.get(row["rank"])
        if rank_id is None:
            rank_id = database.execute(
                "INSERT INTO path_rank (path_definition_id,rank,name) VALUES (?,?,?)",
                (definition["id"], row["rank"], row["name"]),
            ).lastrowid
            ranks[row["rank"]] = rank_id
        if (row["support"] == "manual" and not row["effect_manual"]
                and not row["frequency"] and not row["activation"]):
            continue
        migrate_capability(database, definition["stable_key"], rank_id, row)


def refresh_definition(database, definition):
    database.execute("DELETE FROM path_rank WHERE path_definition_id = ?", (definition["id"],))
    migrate_definition(database, definition)


def migrate_capability(database, path_key, rank_id, row):
    position = database.execute(
        "SELECT COUNT(*) FROM path_capability WHERE path_rank_id = ?", (rank_id,)
    ).fetchone()[0]
    trigger = json.loads(row["trigger_json"]) if row["trigger_json"] else {}
    mode = execution_mode(row, trigger)
    capability_id = database.execute(
        "INSERT INTO path_capability "
        "(path_rank_id,stable_key,name,execution_mode,action_cost,"
        "trigger_event,activation_limit,uses_maximum,recharge,position) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (rank_id, f"{path_key}.rank-{row['rank']}.{row['mode']}", row["name"], mode,
         action_cost(row["activation"]), trigger.get("type"), normalized_limit(row["frequency"]),
         row["uses_maximum"], row["recharge"], position),
    ).lastrowid
    targeting = json.loads(row["targeting_json"] or "{}")
    insert_target(database, capability_id, targeting)
    root_id = database.execute(
        "INSERT INTO effect_node (capability_id,node_type,label,position) "
        "VALUES (?,'sequence','Effets',0)", (capability_id,),
    ).lastrowid
    operations = database.execute(
        "SELECT * FROM path_operation WHERE rank_definition_id = ? AND enabled = 1 "
        "ORDER BY position", (row["id"],),
    ).fetchall()
    for operation in operations:
        migrate_operation(database, capability_id, root_id, operation, targeting)
    if row["effect_manual"] and database.execute(
            "SELECT 1 FROM effect_node WHERE capability_id=? AND node_type='manual_effect' "
            "AND trim(label)=trim(?)", (capability_id, row["effect_manual"]),
    ).fetchone() is None:
        database.execute(
            "INSERT INTO effect_node (capability_id,parent_id,node_type,label,position) "
            "VALUES (?,?,'manual_effect',?,?)",
            (capability_id, root_id, row["effect_manual"], len(operations)),
        )


def execution_mode(row, trigger):
    if trigger.get("type"):
        return "triggered"
    if row["mode"] == "passive":
        return "permanent" if (row["frequency"] or "Permanent") == "Permanent" else "triggered"
    return "activated"


def action_cost(value):
    return {
        "Action": "action", "action": "action", "Action bonus": "bonus_action",
        "bonus_action": "bonus_action", "Réaction": "reaction", "reaction": "reaction",
        "Libre": "free", "free": "free",
    }.get(value, "none")


def insert_target(database, capability_id, targeting):
    selector = targeting.get("selector", "self")
    modes = {"self": "none", "single": "manual", "multiple": "manual", "all": "area"}
    minimum = 0 if selector == "self" else 1
    maximum = 1 if selector == "single" else None
    allegiance = (targeting.get("allegiance") or ["any"])[0]
    area = targeting.get("area") or {}
    distance = area.get("distance") or targeting.get("range") or {}
    database.execute(
        "INSERT INTO capability_target "
        "(capability_id,selection_mode,minimum_targets,maximum_targets,range_value,range_unit,"
        "allegiance,allow_self,area_shape,area_size) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (capability_id, modes.get(selector, "manual"), minimum, maximum,
         distance.get("value"), distance.get("unit"), allegiance,
         int(selector == "self" or targeting.get("include_self", False)),
         area.get("shape"), (area.get("distance") or {}).get("value")),
    )


def migrate_operation(database, capability_id, root_id, row, targeting):
    parameters = json.loads(row["parameters_json"] or "{}")
    old_type = row["operation_type"]
    operation_type = normalized_operation_type(old_type, parameters)
    node_type = "manual_effect" if operation_type == "manual_effect" else "operation"
    node_id = database.execute(
        "INSERT INTO effect_node (capability_id,parent_id,node_type,label,position) "
        "VALUES (?,?,?,?,?)",
        (capability_id, root_id, node_type, parameters.get("description", ""), row["position"]),
    ).lastrowid
    if node_type == "manual_effect":
        return
    value = parameters.get("value")
    dice, fixed = numeric_value(value)
    duration = parameters.get("duration") or {}
    distance = parameters.get("distance") or {}
    database.execute(
        "INSERT INTO effect_operation "
        "(node_id,operation_type,target_ref,value_mode,fixed_value,dice_count,dice_sides,"
        "resource_ref,value_ref,damage_type,status_ref,operation_mode,distance_value,"
        "distance_unit,duration_value,duration_unit,frequency,condition_type,description) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (node_id, operation_type, target_reference(row["target"], targeting),
         "dice" if dice else "fixed", fixed, dice.get("count") if dice else None,
         dice.get("sides") if dice else None, parameters.get("resource"),
         normalized_value_ref(parameters.get("stat")), parameters.get("damage_type"),
         parameters.get("status"),
         parameters.get("operation") or parameters.get("mode"), distance.get("value"),
         distance.get("unit"), duration.get("value"), duration.get("unit"),
         parameters.get("frequency"), (parameters.get("condition") or {}).get("type"),
         parameters.get("description", "")),
    )


def normalized_operation_type(old_type, parameters):
    if old_type == "custom_ability":
        return "manual_effect"
    if old_type == "modify_resource":
        if parameters.get("resource") == "temporary_health":
            return "temporary_health"
        return {"add": "heal", "subtract": "health_cost", "set_minimum": "health_floor"}.get(
            parameters.get("operation"), "modify_value"
        )
    if old_type == "damage" and parameters.get("mode") == "attach":
        return "modify_attack_damage"
    if old_type == "modify_stat":
        return "modify_value"
    if old_type == "modify_protection":
        if parameters.get("status"):
            return "grant_immunity"
        if parameters.get("defense"):
            return "ignore_defense"
        return "reflect_damage" if parameters.get("reflect") else "reduce_damage"
    return old_type


def normalized_limit(value):
    return {"Permanent": None, "1/tour": "once_per_turn", "Premier tour": "first_turn",
            "À volonté": "at_will", "1 fois par Repos au Feu": None}.get(value, value)


def normalized_value_ref(value):
    return {"movement.speed": "movement.walk", "initiative": "initiative.bonus"}.get(value, value)


def target_reference(old_target, targeting):
    if old_target == "self" or targeting.get("selector", "self") == "self":
        return "source"
    return "target.all" if targeting.get("selector") in {"multiple", "all"} else "target.primary"


def numeric_value(value):
    if not isinstance(value, dict):
        return {}, value if isinstance(value, (int, float)) else None
    dice = value.get("dice") or []
    if isinstance(dice, dict):
        dice = [dice]
    return (dice[0] if dice else {}), value.get("constant", 0)


def execution_support(operations):
    supported = sum(item["operation_type"] in EXECUTABLE_OPERATIONS
                    and item["target_ref"] == "source" for item in operations)
    if not supported:
        return "none"
    return "full" if supported == len(operations) else "partial"


def load_normalized_path(database, definition):
    rank_rows = database.execute(
        "SELECT * FROM path_rank WHERE path_definition_id = ? ORDER BY rank",
        (definition["id"],),
    ).fetchall()
    owner_column = "class_id" if definition["origin_type"] == "class" else "species_id"
    return {
        "id": definition["legacy_path_id"], "definition_id": definition["id"],
        "stable_key": definition["stable_key"], owner_column: definition["origin_id"],
        "name": definition["name"], "abilities": definition["abilities"],
        "path_type": definition["origin_type"],
        "ranks": [load_rank(database, row, definition["stable_key"]) for row in rank_rows],
    }


def load_rank(database, row, path_key):
    capability_rows = database.execute(
        "SELECT * FROM path_capability WHERE path_rank_id = ? ORDER BY position, id",
        (row["id"],),
    ).fetchall()
    details = [load_capability(database, item) for item in capability_rows]
    result = {
        "id": f"{path_key}.rank-{row['rank']}", "rank": row["rank"],
        "name": row["name"], "unlock_level": row["unlock_level"],
        "capability_details": details,
        "capabilities": [item["contract"] for item in details],
        "active": None, "passive": None,
    }
    for detail in details:
        mode = "passive" if detail["execution_mode"] == "permanent" else "active"
        result[mode] = result[mode] or legacy_detail(detail, mode)
    return result


def load_capability(database, row):
    target = database.execute(
        "SELECT * FROM capability_target WHERE capability_id = ?", (row["id"],)
    ).fetchone()
    operation_rows = database.execute(
        "SELECT eo.*, en.position FROM effect_operation eo JOIN effect_node en "
        "ON en.id = eo.node_id WHERE en.capability_id = ? ORDER BY en.position",
        (row["id"],),
    ).fetchall()
    manual_rows = database.execute(
        "SELECT label,position FROM effect_node WHERE capability_id = ? "
        "AND node_type = 'manual_effect' ORDER BY position", (row["id"],),
    ).fetchall()
    operations = [dict(item) for item in operation_rows]
    manual_effects = [
        {"operation_type": "manual_effect", "target_ref": "source",
         "description": item["label"], "label": item["label"],
         "position": item["position"]}
        for item in manual_rows
    ]
    support_items = operations + [{"operation_type": "manual_effect", "target_ref": "source"}
                                  for _item in manual_rows]
    support = execution_support(support_items)
    targeting = target_contract(target)
    ordered_effects = sorted(operations + manual_effects, key=lambda item: item["position"])
    contract_operations = [contract_operation(item) for item in ordered_effects]
    contract = {
        "id": row["stable_key"], "support": "full",
        "targeting": targeting, "operations": contract_operations,
    }
    if row["uses_maximum"]:
        contract["uses"] = {"maximum": row["uses_maximum"], "recharge": row["recharge"]}
    generated = describe_capability(contract) if contract_operations else ""
    description_items = describe_capability_items(contract)
    description = generated
    return {
        "id": row["id"], "stable_key": row["stable_key"], "name": row["name"],
        "execution_mode": row["execution_mode"], "action_cost": row["action_cost"],
        "execution_support": support, "description": description,
        "description_items": description_items,
        "execution_mode_label": EXECUTION_MODE_LABELS[row["execution_mode"]],
        "action_cost_label": ACTION_COST_LABELS[row["action_cost"]],
        "uses_label": capability_uses_label(row["uses_maximum"], row["recharge"]),
        "trigger_event": row["trigger_event"],
        "activation_limit": (None if row["execution_mode"] == "permanent"
                             else row["activation_limit"]),
        "uses_maximum": row["uses_maximum"],
        "recharge": row["recharge"], "targeting": dict(target) if target else {},
        "operations": operations, "manual_effects": manual_effects,
        "editor_operations": ordered_effects,
        "contract": contract,
    }


def contract_operation(item):
    if item["operation_type"] == "manual_effect":
        return {"type": "custom_ability", "target": "self",
                "description": item["description"]}
    return legacy_contract_operation(item)


def capability_uses_label(maximum, recharge):
    if not maximum:
        return "À volonté"
    recovery = RECHARGE_LABELS.get(recharge, "récupération non définie")
    return f"{maximum} fois · Récupération : {recovery}"


def target_contract(row):
    if row is None or row["selection_mode"] == "none":
        return {"selector": "self"}
    selector = "all" if row["selection_mode"] == "area" else (
        "single" if row["maximum_targets"] == 1 else "multiple"
    )
    result = {"selector": selector}
    if row["allegiance"] and row["allegiance"] != "any":
        result["allegiance"] = [row["allegiance"]]
    if row["range_value"] is not None:
        result["range"] = {
            "value": row["range_value"],
            "unit": row["range_unit"] or "meter",
        }
    if row["selection_mode"] == "area" and row["area_size"] is not None:
        result["area"] = {
            "shape": row["area_shape"] or "radius",
            "distance": {
                "value": row["area_size"],
                "unit": row["range_unit"] or "meter",
            },
        }
    return result


def legacy_contract_operation(row):
    operation_type = row["operation_type"]
    result = {"type": legacy_operation_type(operation_type),
              "target": "self" if row["target_ref"] == "source" else "selected",
              "target_ref": row["target_ref"]}
    if operation_type in {"damage", "modify_attack_damage"}:
        result.update(damage_type=row["damage_type"] or "physical",
                      value=contract_value(row))
        if operation_type == "modify_attack_damage":
            result["mode"] = "attach"
    elif operation_type in {"heal", "health_cost", "health_floor", "temporary_health"}:
        result.update(resource="temporary_health" if operation_type == "temporary_health"
                      else "health", value=contract_value(row),
                      operation={"health_cost": "subtract", "health_floor": "set_minimum"}.get(
                          operation_type, "add"))
    elif operation_type == "modify_value":
        result.update(stat=row["value_ref"] or "value", value=row["fixed_value"] or 0,
                      operation=row["operation_mode"] or "add")
    elif operation_type == "apply_status":
        result["status"] = row["status_ref"] or "non défini"
    elif operation_type in {"reduce_damage", "reflect_damage"}:
        result["value"] = contract_value(row)
        if operation_type == "reflect_damage":
            result["reflect"] = True
    elif operation_type == "grant_immunity":
        result["status"] = row["status_ref"] or "non défini"
    elif operation_type == "ignore_defense":
        result["defense"] = (row["value_ref"] or "physical").removeprefix("defense.")
        result["value"] = int(row["fixed_value"]) if row["fixed_value"] is not None else None
    elif operation_type == "move":
        result["distance"] = {"value": row["distance_value"],
                              "unit": row["distance_unit"] or "meter"}
        if row["operation_mode"] == "away":
            result["direction"] = "away"
    elif operation_type == "extra_attack":
        result["count"] = int(row["fixed_value"] or 1)
    else:
        result["description"] = row["description"] or operation_type
    if row["duration_value"]:
        result["duration"] = {"value": row["duration_value"],
                              "unit": row["duration_unit"] or "turn"}
    if row["frequency"]:
        result["frequency"] = row["frequency"]
    if row["condition_type"]:
        result["condition"] = {"type": row["condition_type"]}
    return result


def legacy_operation_type(operation_type):
    return {
        "modify_attack_damage": "damage", "heal": "modify_resource",
        "health_cost": "modify_resource", "temporary_health": "modify_resource",
        "health_floor": "modify_resource",
        "modify_value": "modify_stat", "manual_effect": "custom_ability",
        "reduce_damage": "modify_protection", "grant_immunity": "modify_protection",
        "ignore_defense": "modify_protection", "reflect_damage": "modify_protection",
    }.get(operation_type, operation_type)


def contract_value(row):
    dice = ([{"count": row["dice_count"], "sides": row["dice_sides"]}]
            if row["dice_count"] else [])
    return {"dice": dice, "terms": [], "constant": int(row["fixed_value"] or 0)}


def legacy_detail(capability, mode):
    detail = {"effect": capability["description"],
              "automation": {"level": capability["execution_support"],
                             "effects": executable_effects(capability["operations"])}}
    if mode == "passive":
        detail["frequency"] = capability["activation_limit"] or "Permanent"
        return detail
    labels = {"action": "Action", "bonus_action": "Action bonus",
              "reaction": "Réaction", "free": "Libre", "none": "Aucun"}
    detail.update(timing=labels[capability["action_cost"]],
                  uses=legacy_uses(capability["uses_maximum"], capability["recharge"]))
    if capability["uses_maximum"]:
        detail["resource"] = {"id": f"{capability['stable_key']}.uses",
                              "maximum": capability["uses_maximum"],
                              "recovery": [capability["recharge"]]}
    return detail


def executable_effects(operations):
    effects = []
    for operation in operations:
        if (operation["operation_type"] not in EXECUTABLE_OPERATIONS
                or operation["target_ref"] != "source"):
            continue
        effects.append({
            "type": {"damage": "deal_damage", "heal": "heal",
                     "health_cost": "health_cost"}[operation["operation_type"]],
            "value": {"dice": {"count": int(operation["dice_count"] or 0),
                                 "sides": int(operation["dice_sides"] or 1)},
                      "bonus": int(operation["fixed_value"] or 0)},
        })
    return effects


def legacy_uses(maximum, recharge):
    if not maximum:
        return "À volonté"
    rest = "Repos court" if recharge == "short_rest" else "Repos au Feu"
    return f"{maximum} fois par {rest}"


def find_capability(database, path_definition_id, capability_id):
    return database.execute(
        "SELECT pc.*, pr.rank, pr.path_definition_id FROM path_capability pc "
        "JOIN path_rank pr ON pr.id = pc.path_rank_id "
        "WHERE pc.id = ? AND pr.path_definition_id = ?",
        (capability_id, path_definition_id),
    ).fetchone()


def save_capability(database, path_definition_id, rank_number, values, capability_id=None):
    rank = database.execute(
        "SELECT id FROM path_rank WHERE path_definition_id = ? AND rank = ?",
        (path_definition_id, rank_number),
    ).fetchone()
    if rank is None:
        rank_id = database.execute(
            "INSERT INTO path_rank (path_definition_id,rank,name) VALUES (?,?,?)",
            (path_definition_id, rank_number, f"Rang {rank_number}"),
        ).lastrowid
    else:
        rank_id = rank["id"]
    if capability_id is None:
        position = database.execute(
            "SELECT COUNT(*) FROM path_capability WHERE path_rank_id = ?", (rank_id,)
        ).fetchone()[0]
        stable_key = f"{values['path_key']}.rank-{rank_number}.{slug_key(values['name'])}-{position + 1}"
        capability_id = database.execute(
            "INSERT INTO path_capability "
            "(path_rank_id,stable_key,name,execution_mode,action_cost,"
            "trigger_event,activation_limit,uses_maximum,recharge,position) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rank_id, stable_key, values["name"], values["execution_mode"],
             values["action_cost"], values["trigger_event"], values["activation_limit"], values["uses_maximum"],
             values["recharge"], position),
        ).lastrowid
    else:
        cursor = database.execute(
            "UPDATE path_capability SET name=?,execution_mode=?,action_cost=?,"
            "trigger_event=?,activation_limit=?,uses_maximum=?,recharge=? "
            "WHERE id=? AND path_rank_id=?",
            (values["name"], values["execution_mode"], values["action_cost"],
             values["trigger_event"], values["activation_limit"], values["uses_maximum"], values["recharge"],
             capability_id, rank_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Capacité introuvable.")
        database.execute("DELETE FROM capability_target WHERE capability_id = ?", (capability_id,))
        database.execute("DELETE FROM effect_node WHERE capability_id = ?", (capability_id,))
    save_target(database, capability_id, values)
    save_effects(database, capability_id, values["operations"])
    database.commit()
    return capability_id


def save_target(database, capability_id, values):
    database.execute(
        "INSERT INTO capability_target "
        "(capability_id,selection_mode,minimum_targets,maximum_targets,range_value,range_unit,"
        "allegiance,entity_type,allow_self,requires_visibility,area_shape,area_size) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (capability_id, values["selection_mode"], values["minimum_targets"],
         values["maximum_targets"], values["range_value"], "meter", values["allegiance"],
         values["entity_type"], int(values["allow_self"]), int(values["requires_visibility"]),
         values["area_shape"], values["area_size"]),
    )


def save_effects(database, capability_id, operations):
    root_id = database.execute(
        "INSERT INTO effect_node (capability_id,node_type,label,position) "
        "VALUES (?,'sequence','Effets',0)", (capability_id,),
    ).lastrowid
    for position, operation in enumerate(operations):
        manual = operation["operation_type"] == "manual_effect"
        node_id = database.execute(
            "INSERT INTO effect_node (capability_id,parent_id,node_type,label,position) "
            "VALUES (?,?,?,?,?)",
            (capability_id, root_id, "manual_effect" if manual else "operation",
             operation["description"] if manual else "", position),
        ).lastrowid
        if manual:
            continue
        columns = (
            "node_id", "operation_type", "target_ref", "value_mode", "fixed_value",
            "dice_count", "dice_sides", "resource_ref", "value_ref", "damage_type",
            "status_ref", "operation_mode", "distance_value", "distance_unit",
            "duration_value", "duration_unit", "expiration", "frequency",
            "condition_type", "description",
        )
        database.execute(
            f"INSERT INTO effect_operation ({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)})",
            tuple([node_id] + [operation.get(column) for column in columns[1:]]),
        )


def delete_capability(database, path_definition_id, capability_id):
    capability = find_capability(database, path_definition_id, capability_id)
    if capability is None:
        return False
    database.execute("DELETE FROM path_capability WHERE id = ?", (capability_id,))
    database.commit()
    return True


def update_rank_metadata(database, path_definition_id, ranks, form):
    for rank in ranks:
        database.execute(
            "UPDATE path_rank SET name=?,unlock_level=? "
            "WHERE path_definition_id=? AND rank=?",
            (rank["name"], optional_int(form.get(f"rank_{rank['rank']}_unlock_level")),
             path_definition_id, rank["rank"]),
        )
    database.commit()


def optional_int(value):
    return int(value) if value not in (None, "") else None


def slug_key(value):
    import re
    import unicodedata
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-") or "capacite"

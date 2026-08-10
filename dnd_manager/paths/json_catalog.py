import json
from pathlib import Path

from dnd_manager.paths.normalized import load_capability, save_effects


CATALOG_VERSION = 1
EFFECT_FIELDS = (
    "operation_type", "target_ref", "value_mode", "fixed_value", "dice_count",
    "dice_sides", "resource_ref", "value_ref", "damage_type", "status_ref",
    "operation_mode", "distance_value", "distance_unit", "duration_value",
    "duration_unit", "expiration", "frequency", "condition_type", "description",
)
CAPABILITY_FIELDS = (
    "name", "execution_mode", "action_cost", "trigger_event", "activation_limit",
    "uses_maximum", "recharge",
)


def synchronize_catalog(database, filename):
    path = Path(filename)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_catalog(database, path)
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    import_catalog(database, payload)


def write_catalog(database, filename):
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = export_catalog(database)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_catalog(database):
    return {
        "schema_version": CATALOG_VERSION,
        "classes": export_origins(database, "character_class"),
        "races": export_origins(database, "species"),
        "voies": export_paths(database),
    }


def export_origins(database, table):
    rows = database.execute(f"SELECT * FROM {table} WHERE configured=1 ORDER BY name").fetchall()
    common = ("stable_key", "name", "description")
    extra = (("hit_die", "strength_bonus", "dexterity_bonus", "constitution_bonus",
              "intelligence_bonus", "wisdom_bonus", "charisma_bonus")
             if table == "character_class" else
             ("traits", "size", "speed", "physical_bonus", "elemental_bonus",
              "spiritual_bonus"))
    return [{key: row[key] for key in common + extra} for row in rows]


def export_paths(database):
    definitions = database.execute(
        "SELECT * FROM path_definition ORDER BY origin_type,origin_id,name"
    ).fetchall()
    return [export_path(database, row) for row in definitions]


def export_path(database, definition):
    owner_table = "character_class" if definition["origin_type"] == "class" else "species"
    owner = database.execute(
        f"SELECT stable_key FROM {owner_table} WHERE id=?", (definition["origin_id"],)
    ).fetchone()
    ranks = database.execute(
        "SELECT * FROM path_rank WHERE path_definition_id=? ORDER BY rank",
        (definition["id"],),
    ).fetchall()
    return {
        "stable_key": definition["stable_key"], "type": definition["origin_type"],
        "origine": owner["stable_key"], "name": definition["name"],
        "abilities": definition["abilities"], "status": definition["status"],
        "rangs": [export_rank(database, rank) for rank in ranks],
    }


def export_rank(database, rank):
    rows = database.execute(
        "SELECT * FROM path_capability WHERE path_rank_id=? ORDER BY position,id", (rank["id"],)
    ).fetchall()
    return {
        "rank": rank["rank"], "name": rank["name"], "unlock_level": rank["unlock_level"],
        "capacites": [export_capability(database, row) for row in rows],
    }


def export_capability(database, row):
    item = load_capability(database, row)
    result = {"stable_key": row["stable_key"]}
    result.update({field: row[field] for field in CAPABILITY_FIELDS})
    result["ciblage"] = targeting_payload(item["targeting"])
    result["effets"] = [
        {field: effect.get(field) for field in EFFECT_FIELDS}
        for effect in item["editor_operations"]
    ]
    return result


def targeting_payload(target):
    fields = ("selection_mode", "minimum_targets", "maximum_targets", "range_value",
              "range_unit", "allegiance", "entity_type", "allow_self",
              "requires_visibility", "area_shape", "area_size")
    return {field: target.get(field) for field in fields}


def import_catalog(database, payload):
    if payload.get("schema_version") != CATALOG_VERSION:
        raise ValueError("Version de catalogue JSON non prise en charge.")
    synchronize_origins(database, "character_class", payload.get("classes", []))
    synchronize_origins(database, "species", payload.get("races", []))
    paths = payload.get("voies", [])
    stage_legacy_path_names(database, paths)
    for path in paths:
        synchronize_path(database, path)
    delete_missing_paths(database, {required(path, "stable_key") for path in paths})
    database.commit()


def stage_legacy_path_names(database, paths):
    """Libère les noms uniques avant un renommage croisé de plusieurs voies."""
    for item in paths:
        row = database.execute(
            "SELECT origin_type,legacy_path_id FROM path_definition WHERE stable_key=?",
            (required(item, "stable_key"),),
        ).fetchone()
        if row is None:
            continue
        table = "class_path" if row["origin_type"] == "class" else "racial_path"
        database.execute(
            f"UPDATE {table} SET name=? WHERE id=?",
            (f"__catalog_sync_{row['legacy_path_id']}__", row["legacy_path_id"]),
        )


def delete_missing_paths(database, kept_keys):
    rows = database.execute(
        "SELECT stable_key,origin_type,legacy_path_id FROM path_definition"
    ).fetchall()
    for row in rows:
        if row["stable_key"] in kept_keys:
            continue
        database.execute("DELETE FROM path_definition WHERE stable_key=?", (row["stable_key"],))
        legacy_table = "class_path" if row["origin_type"] == "class" else "racial_path"
        database.execute(
            f"DELETE FROM {legacy_table} WHERE id=?", (row["legacy_path_id"],)
        )


def synchronize_origins(database, table, items):
    allowed = ({"name", "description", "hit_die", "strength_bonus", "dexterity_bonus",
                "constitution_bonus", "intelligence_bonus", "wisdom_bonus", "charisma_bonus"}
               if table == "character_class" else
               {"name", "description", "traits", "size", "speed", "physical_bonus",
                "elemental_bonus", "spiritual_bonus"})
    for item in items:
        stable_key = required(item, "stable_key")
        values = {key: item[key] for key in sorted(allowed) if key in item}
        if not values:
            continue
        assignments = ",".join(f"{key}=?" for key in values)
        cursor = database.execute(
            f"UPDATE {table} SET {assignments},configured=1 WHERE stable_key=?",
            (*values.values(), stable_key),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Origine inconnue dans le catalogue JSON : {stable_key}")


def synchronize_path(database, item):
    stable_key = required(item, "stable_key")
    path_type = required(item, "type")
    owner_table = "character_class" if path_type == "class" else "species"
    owner = database.execute(
        f"SELECT id FROM {owner_table} WHERE stable_key=?", (required(item, "origine"),)
    ).fetchone()
    definition = database.execute(
        "SELECT * FROM path_definition WHERE stable_key=?", (stable_key,)
    ).fetchone()
    if owner is None or path_type not in {"class", "racial"}:
        raise ValueError(f"Voie ou origine inconnue dans le catalogue JSON : {stable_key}")
    if definition is None:
        definition = create_path(database, item, owner["id"])
    database.execute(
        "UPDATE path_definition SET origin_type=?,origin_id=?,name=?,abilities=?,status=? WHERE id=?",
        (path_type, owner["id"], required(item, "name"), item.get("abilities", ""),
         item.get("status", "published"), definition["id"]),
    )
    update_legacy_path(database, definition, owner["id"], item)
    synchronize_ranks(database, definition["id"], item.get("rangs", []))


def create_path(database, item, owner_id):
    table, owner_column = (("class_path", "class_id") if item["type"] == "class"
                           else ("racial_path", "species_id"))
    cursor = database.execute(
        f"INSERT INTO {table} ({owner_column},name,abilities,ranks_json,configured,stable_key) "
        "VALUES (?,?,?,'[]',1,?)",
        (owner_id, item["name"], item.get("abilities", ""), item["stable_key"]),
    )
    definition_id = database.execute(
        "INSERT INTO path_definition "
        "(stable_key,origin_type,origin_id,legacy_path_id,name,abilities,status) "
        "VALUES (?,?,?,?,?,?,?)",
        (item["stable_key"], item["type"], owner_id, cursor.lastrowid, item["name"],
         item.get("abilities", ""), item.get("status", "published")),
    ).lastrowid
    return database.execute("SELECT * FROM path_definition WHERE id=?", (definition_id,)).fetchone()


def update_legacy_path(database, definition, owner_id, item):
    table, owner_column = (("class_path", "class_id") if item["type"] == "class"
                           else ("racial_path", "species_id"))
    database.execute(
        f"UPDATE {table} SET {owner_column}=?,name=?,abilities=?,configured=1 WHERE id=?",
        (owner_id, item["name"], item.get("abilities", ""), definition["legacy_path_id"]),
    )


def synchronize_ranks(database, definition_id, items):
    kept = []
    for item in items:
        number = int(required(item, "rank"))
        row = database.execute(
            "SELECT id FROM path_rank WHERE path_definition_id=? AND rank=?",
            (definition_id, number),
        ).fetchone()
        if row is None:
            rank_id = database.execute(
                "INSERT INTO path_rank (path_definition_id,rank,name,unlock_level) VALUES (?,?,?,?)",
                (definition_id, number, required(item, "name"), item.get("unlock_level")),
            ).lastrowid
        else:
            rank_id = row["id"]
            database.execute(
                "UPDATE path_rank SET name=?,unlock_level=? WHERE id=?",
                (required(item, "name"), item.get("unlock_level"), rank_id),
            )
        kept.append(rank_id)
        synchronize_capabilities(database, rank_id, item.get("capacites", []))
    delete_missing(database, "path_rank", "path_definition_id", definition_id, kept)


def synchronize_capabilities(database, rank_id, items):
    database.execute(
        "UPDATE path_capability SET position=position+100000 WHERE path_rank_id=?", (rank_id,)
    )
    kept = []
    for position, item in enumerate(items):
        stable_key = required(item, "stable_key")
        row = database.execute(
            "SELECT id FROM path_capability WHERE stable_key=?", (stable_key,)
        ).fetchone()
        values = tuple(item.get(field) for field in CAPABILITY_FIELDS)
        if row is None:
            capability_id = database.execute(
                "INSERT INTO path_capability (path_rank_id,stable_key,"
                + ",".join(CAPABILITY_FIELDS) + ",position) VALUES (?,?,"
                + ",".join("?" for _field in CAPABILITY_FIELDS) + ",?)",
                (rank_id, stable_key, *values, position),
            ).lastrowid
        else:
            capability_id = row["id"]
            assignments = ",".join(f"{field}=?" for field in CAPABILITY_FIELDS)
            database.execute(
                f"UPDATE path_capability SET path_rank_id=?,{assignments},position=? WHERE id=?",
                (rank_id, *values, position, capability_id),
            )
            database.execute("DELETE FROM capability_target WHERE capability_id=?", (capability_id,))
            database.execute("DELETE FROM effect_node WHERE capability_id=?", (capability_id,))
        kept.append(capability_id)
        save_json_target(database, capability_id, item.get("ciblage", {}))
        save_effects(database, capability_id, item.get("effets", []))
    delete_missing(database, "path_capability", "path_rank_id", rank_id, kept)


def save_json_target(database, capability_id, target):
    fields = ("selection_mode", "minimum_targets", "maximum_targets", "range_value",
              "range_unit", "allegiance", "entity_type", "allow_self",
              "requires_visibility", "area_shape", "area_size")
    defaults = ("none", 0, None, None, "meter", "any", "creature", 0, 1, None, None)
    values = [target.get(field, default) for field, default in zip(fields, defaults)]
    columns = ",".join(("capability_id", *fields))
    placeholders = ",".join("?" for _field in ("capability_id", *fields))
    database.execute(
        f"INSERT INTO capability_target ({columns}) VALUES ({placeholders})",
        (capability_id, *values),
    )


def delete_missing(database, table, parent_column, parent_id, kept):
    if kept:
        placeholders = ",".join("?" for _item in kept)
        database.execute(
            f"DELETE FROM {table} WHERE {parent_column}=? AND id NOT IN ({placeholders})",
            (parent_id, *kept),
        )
    else:
        database.execute(f"DELETE FROM {table} WHERE {parent_column}=?", (parent_id,))


def required(item, key):
    value = item.get(key)
    if value in (None, ""):
        raise ValueError(f"Champ obligatoire absent du catalogue JSON : {key}")
    return value

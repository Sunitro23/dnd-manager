import json
import re
from pathlib import Path

from dnd_manager.campaign.path_schema import describe_capability, legacy_capabilities


CANONICAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS path_definition (
 id INTEGER PRIMARY KEY, stable_key TEXT NOT NULL UNIQUE,
 origin_type TEXT NOT NULL CHECK (origin_type IN ('class','racial')),
 origin_id INTEGER NOT NULL, legacy_path_id INTEGER NOT NULL,
 name TEXT NOT NULL COLLATE NOCASE, abilities TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft','published','archived')),
 UNIQUE(origin_type, legacy_path_id));
CREATE TABLE IF NOT EXISTS path_rank_definition (
 id INTEGER PRIMARY KEY, path_definition_id INTEGER NOT NULL REFERENCES path_definition(id) ON DELETE CASCADE,
 rank INTEGER NOT NULL CHECK(rank > 0), name TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('active','passive')),
 support TEXT NOT NULL CHECK(support IN ('manual','partial','full')),
 activation TEXT, frequency TEXT, effect_manual TEXT NOT NULL DEFAULT '',
 uses_maximum INTEGER, recharge TEXT, targeting_json TEXT NOT NULL DEFAULT '{"selector":"self"}',
 trigger_json TEXT, UNIQUE(path_definition_id,rank,mode));
CREATE TABLE IF NOT EXISTS path_operation (
 id INTEGER PRIMARY KEY, rank_definition_id INTEGER NOT NULL REFERENCES path_rank_definition(id) ON DELETE CASCADE,
 position INTEGER NOT NULL CHECK(position >= 0), operation_type TEXT NOT NULL,
 target TEXT NOT NULL DEFAULT 'selected', parameters_json TEXT NOT NULL DEFAULT '{}',
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), UNIQUE(rank_definition_id,position));
"""


def ensure_schema(database):
    row = database.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' "
        "AND name = 'path_rank_definition'"
    ).fetchone()
    if row and "UNIQUE(path_definition_id,rank)" in row["sql"].replace(" ", ""):
        database.execute("DROP TABLE IF EXISTS path_operation")
        database.execute("DROP TABLE path_rank_definition")
    database.executescript(CANONICAL_SCHEMA)
    # schema.sql ne contient que des créations idempotentes. Il installe également
    # le modèle normalisé rang -> capacités -> arbre d’effets sur les bases existantes.
    database.executescript(
        (Path(__file__).parents[2] / "schema.sql").read_text(encoding="utf-8")
    )
    from dnd_manager.paths.normalized import migrate_existing_capabilities
    migrate_existing_capabilities(database)


def migrate_legacy_paths(database):
    ensure_schema(database)
    for path_type, table, owner_column in (
        ("class", "class_path", "class_id"),
        ("racial", "racial_path", "species_id"),
    ):
        rows = database.execute(f"SELECT * FROM {table}").fetchall()
        for row in rows:
            migrate_legacy_path(database, path_type, owner_column, row)
    database.commit()


def migrate_legacy_path(database, path_type, owner_column, row):
    ranks = json.loads(row["ranks_json"])
    first_rank_id = ranks[0].get("id", "") if ranks else ""
    inferred_key = first_rank_id.rsplit(".rank-", 1)[0] if ".rank-" in first_rank_id else ""
    existing = database.execute(
        "SELECT stable_key FROM path_definition "
        "WHERE origin_type = ? AND legacy_path_id = ?", (path_type, row["id"]),
    ).fetchone()
    stable_key = ((existing["stable_key"] if existing else None) or row["stable_key"]
                  or inferred_key or f"path.custom-{path_type}-{row['id']}")
    database.execute(
        "INSERT INTO path_definition "
        "(stable_key,origin_type,origin_id,legacy_path_id,name,abilities,status) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(stable_key) DO UPDATE SET "
        "origin_type=excluded.origin_type,origin_id=excluded.origin_id,"
        "legacy_path_id=excluded.legacy_path_id,name=excluded.name,abilities=excluded.abilities,"
        "status=excluded.status",
        (stable_key, path_type, row[owner_column], row["id"], row["name"], row["abilities"],
         "published" if row["configured"] else "archived"),
    )
    definition_id = database.execute(
        "SELECT id FROM path_definition WHERE stable_key = ?", (stable_key,)
    ).fetchone()["id"]
    database.execute(
        "DELETE FROM path_rank_definition WHERE path_definition_id = ?", (definition_id,)
    )
    for rank in ranks:
        migrate_rank(database, definition_id, stable_key, rank)
    if database.execute(
        "SELECT 1 FROM path_rank WHERE path_definition_id = ? LIMIT 1", (definition_id,)
    ).fetchone() is None:
        from dnd_manager.paths.normalized import migrate_definition
        definition = database.execute(
            "SELECT id, stable_key FROM path_definition WHERE id = ?", (definition_id,)
        ).fetchone()
        migrate_definition(database, definition)


def migrate_rank(database, definition_id, path_key, rank):
    capabilities = rank.get("capabilities") or legacy_capabilities(path_key, rank)
    if not capabilities:
        database.execute(
            "INSERT INTO path_rank_definition "
            "(path_definition_id,rank,name,mode,support,effect_manual,targeting_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (definition_id, rank["rank"], rank["name"], "passive", "manual", "", "{}"),
        )
        return
    for capability in capabilities:
        migrate_capability(database, definition_id, rank, capability)


def migrate_capability(database, definition_id, rank, capability):
    mode = capability["id"].rsplit(".", 1)[-1]
    detail, uses = rank.get(mode) or {}, capability.get("uses") or {}
    resource = detail.get("resource") or {}
    if not uses and resource.get("maximum"):
        recoveries = resource.get("recovery") or []
        uses = {"maximum": resource["maximum"],
                "recharge": recoveries[-1] if recoveries else "long_rest"}
    if not uses:
        match = re.search(r"(\d+)\s+(?:fois|charges?)\s+par\s+Repos", detail.get("uses", ""))
        if match:
            uses = {"maximum": int(match.group(1)),
                    "recharge": "short_rest" if "Repos court" in detail["uses"]
                    else "long_rest"}
    cursor = database.execute(
        "INSERT INTO path_rank_definition "
        "(path_definition_id,rank,name,mode,support,activation,frequency,effect_manual,"
        "uses_maximum,recharge,targeting_json,trigger_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (definition_id, rank["rank"], rank["name"], mode, capability["support"],
         (detail.get("activation") or {}).get("type") or detail.get("timing"),
         detail.get("frequency"), detail.get("effect", "")
         if capability["support"] != "full" else "", uses.get("maximum"),
         uses.get("recharge"), json.dumps(capability["targeting"], ensure_ascii=False),
         json.dumps({**(capability.get("trigger") or {}),
                     **({"resource_id": resource["id"]} if resource.get("id") else {})},
                    ensure_ascii=False)
         if capability.get("trigger") or resource.get("id") else None),
    )
    for position, operation in enumerate(capability["operations"]):
        parameters = {key: value for key, value in operation.items()
                      if key not in {"type", "target", "enabled"}}
        database.execute(
            "INSERT INTO path_operation "
            "(rank_definition_id,position,operation_type,target,parameters_json,enabled) "
            "VALUES (?,?,?,?,?,?)", (cursor.lastrowid, position, operation["type"],
             operation.get("target", "selected"), json.dumps(parameters, ensure_ascii=False),
             int(operation.get("enabled", True))),
        )


def list_paths(database, path_type=None, status="published"):
    clauses, parameters = ["status = ?"], [status]
    if path_type:
        clauses.append("origin_type = ?")
        parameters.append(path_type)
    rows = database.execute(
        f"SELECT * FROM path_definition WHERE {' AND '.join(clauses)} "
        "ORDER BY origin_id, name COLLATE NOCASE", parameters,
    ).fetchall()
    from dnd_manager.paths.normalized import load_normalized_path
    return [load_normalized_path(database, row) for row in rows]


def paths_for_origin(database, path_type, origin_id):
    migrate_missing_legacy_paths(database, path_type, origin_id)
    rows = database.execute(
        "SELECT * FROM path_definition WHERE origin_type = ? AND origin_id = ? "
        "AND status = 'published' ORDER BY name COLLATE NOCASE", (path_type, origin_id),
    ).fetchall()
    from dnd_manager.paths.normalized import load_normalized_path
    return [load_normalized_path(database, row) for row in rows]


def migrate_missing_legacy_paths(database, path_type, origin_id):
    legacy_table, owner_column = (("class_path", "class_id") if path_type == "class"
                                  else ("racial_path", "species_id"))
    rows = database.execute(
        f"SELECT legacy.* FROM {legacy_table} legacy "
        "LEFT JOIN path_definition canonical "
        "ON canonical.origin_type = ? AND canonical.legacy_path_id = legacy.id "
        f"WHERE legacy.{owner_column} = ? AND legacy.configured = 1 "
        "AND canonical.id IS NULL",
        (path_type, origin_id),
    ).fetchall()
    for row in rows:
        migrate_legacy_path(database, path_type, owner_column, row)
    if rows:
        database.commit()


def find_path(database, path_type, legacy_path_id):
    row = database.execute(
        "SELECT * FROM path_definition WHERE origin_type = ? AND legacy_path_id = ?",
        (path_type, legacy_path_id),
    ).fetchone()
    if row is None:
        legacy_table, owner_column = (("class_path", "class_id") if path_type == "class"
                                      else ("racial_path", "species_id"))
        legacy = database.execute(
            f"SELECT * FROM {legacy_table} WHERE id = ? AND configured = 1",
            (legacy_path_id,),
        ).fetchone()
        if legacy:
            migrate_legacy_path(database, path_type, owner_column, legacy)
            database.commit()
            row = database.execute(
                "SELECT * FROM path_definition WHERE origin_type = ? AND legacy_path_id = ?",
                (path_type, legacy_path_id),
            ).fetchone()
    if row is None:
        return None
    from dnd_manager.paths.normalized import load_normalized_path
    return load_normalized_path(database, row)


def assembled_path(database, row):
    ranks = database.execute(
        "SELECT * FROM path_rank_definition WHERE path_definition_id = ? ORDER BY rank",
        (row["id"],),
    ).fetchall()
    operations = database.execute(
        "SELECT po.* FROM path_operation po JOIN path_rank_definition pr "
        "ON pr.id = po.rank_definition_id WHERE pr.path_definition_id = ? "
        "AND po.enabled = 1 ORDER BY po.rank_definition_id, po.position", (row["id"],),
    ).fetchall()
    operations_by_rank = {}
    for operation in operations:
        operations_by_rank.setdefault(operation["rank_definition_id"], []).append(operation)
    owner_column = "class_id" if row["origin_type"] == "class" else "species_id"
    return {"id": row["legacy_path_id"], "definition_id": row["id"],
            "stable_key": row["stable_key"], owner_column: row["origin_id"],
            "name": row["name"], "abilities": row["abilities"],
            "path_type": row["origin_type"],
            "ranks": assembled_ranks(ranks, operations_by_rank, row["stable_key"])}


def assembled_ranks(rows, operations_by_rank, path_key):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["rank"], []).append(row)
    return [assembled_rank(grouped[number], operations_by_rank, path_key)
            for number in sorted(grouped)]


def assembled_rank(rows, operations_by_rank, path_key):
    primary = rows[0]
    result = {"id": f"{path_key}.rank-{primary['rank']}", "rank": primary["rank"],
              "name": primary["name"], "active": None, "passive": None,
              "capabilities": []}
    for row in rows:
        if (row["support"] == "manual" and not row["effect_manual"]
                and not row["frequency"] and not operations_by_rank.get(row["id"])):
            continue
        detail, capability = assembled_capability(
            row, operations_by_rank.get(row["id"], ()), path_key,
        )
        result[row["mode"]] = detail
        result["capabilities"].append(capability)
    return result


def assembled_capability(row, operations, path_key):
    capability = {"id": f"{path_key}.rank-{row['rank']}.{row['mode']}",
                  "support": row["support"],
                  "targeting": json.loads(row["targeting_json"]),
                  "operations": [assembled_operation(item) for item in operations]}
    if row["uses_maximum"]:
        capability["uses"] = {"maximum": row["uses_maximum"], "recharge": row["recharge"]}
    effect = (describe_capability(capability) if row["support"] == "full"
              else row["effect_manual"])
    detail = {"effect": effect, "automation": {"level": row["support"], "effects": []}}
    if row["mode"] == "active":
        activation_labels = {"action": "Action", "bonus_action": "Action bonus",
                             "reaction": "Réaction", "free": "Libre"}
        detail.update(timing=activation_labels.get(row["activation"], row["activation"] or "Action"),
                      uses=legacy_uses_label(row["uses_maximum"], row["recharge"]))
        if row["uses_maximum"]:
            metadata = json.loads(row["trigger_json"]) if row["trigger_json"] else {}
            detail["resource"] = {
                "id": metadata.get("resource_id", f"{capability['id']}.uses"),
                "maximum": row["uses_maximum"],
                "recovery": [row["recharge"]],
            }
    else:
        detail["frequency"] = row["frequency"] or "Permanent"
    return detail, capability


def assembled_operation(row):
    return {"type": row["operation_type"], "target": row["target"],
            **json.loads(row["parameters_json"])}


def legacy_uses_label(maximum, recharge):
    if not maximum:
        return "À volonté"
    rest = "Repos court" if recharge == "short_rest" else "Repos au Feu"
    return f"{maximum} fois par {rest}"

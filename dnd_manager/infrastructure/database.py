import sqlite3
from pathlib import Path

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = connect_database(current_app.config["DATABASE_PATH"])
    return g.db


def connect_database(path):
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    return enable_foreign_keys(database)


def enable_foreign_keys(database):
    database.execute("PRAGMA foreign_keys = ON")
    return database


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db():
    database = get_db()
    database.executescript(project_file("schema.sql").read_text(encoding="utf-8"))
    _migrate_existing_database(database)
    sync_game_config(database)


def project_file(name):
    return Path(__file__).parents[2] / name


def table_columns(database, table):
    return {
        row["name"]
        for row in database.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _extend_character_score_range(database):
    """Rebuild the legacy table because SQLite cannot alter CHECK constraints."""
    create_sql = extended_character_sql()
    old_columns = table_columns(database, "character")
    rebuild_character_table(database, create_sql, old_columns)


def extended_character_sql():
    schema = project_file("schema.sql").read_text(encoding="utf-8")
    start = schema.index("CREATE TABLE IF NOT EXISTS character (")
    end = schema.index("\n);", start) + 3
    return schema[start:end].replace("CREATE TABLE IF NOT EXISTS character (",
                                     "CREATE TABLE character_extended (", 1)


def rebuild_character_table(database, create_sql, old_columns):
    prepare_rebuild(database)
    try:
        replace_character_table(database, create_sql, old_columns)
    finally:
        database.execute("PRAGMA foreign_keys = ON")


def prepare_rebuild(database):
    database.commit()
    database.execute("PRAGMA foreign_keys = OFF")


def replace_character_table(database, create_sql, old_columns):
    database.execute(create_sql)
    columns = ", ".join(sorted(old_columns & table_columns(database, "character_extended")))
    copy_character_columns(database, columns)
    rename_extended_character(database)
    restore_character_indexes(database)


def rename_extended_character(database):
    database.execute("DROP TABLE character")
    database.execute("ALTER TABLE character_extended RENAME TO character")


def copy_character_columns(database, columns):
    query = f"INSERT INTO character_extended ({columns}) SELECT {columns} FROM character"
    database.execute(query)


def restore_character_indexes(database):
    database.execute("CREATE INDEX IF NOT EXISTS character_public_list "
                     "ON character (visibility, character_type, name)")
    database.execute("CREATE INDEX IF NOT EXISTS character_owner ON character (owner_id)")
    database.commit()


def _migrate_existing_database(database):
    migrate_catalogue_columns(database)
    migrate_character_columns(database)
    migrate_removed_features(database)
    migrate_equipment(database)
    database.commit()


def migrate_catalogue_columns(database):
    abilities = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
    class_specs = tuple((f"{field}_bonus", "INTEGER NOT NULL DEFAULT 0") for field in abilities)
    add_missing_columns(database, "character_class", class_specs + (("configured", "INTEGER NOT NULL DEFAULT 0"),))
    add_missing_columns(database, "species", (("stable_key", "TEXT"),))
    add_missing_columns(database, "class_path", (("stable_key", "TEXT"),))
    add_missing_columns(database, "racial_path", (("stable_key", "TEXT"),))
    path_defenses = tuple((f"{name}_bonus", "INTEGER NOT NULL DEFAULT 0")
                          for name in ("physical", "elemental", "spiritual"))
    add_missing_columns(database, "racial_path", path_defenses)
    species = ("physical_bonus", "elemental_bonus", "spiritual_bonus", "configured")
    add_missing_columns(database, "species", tuple((name, "INTEGER NOT NULL DEFAULT 0") for name in species))


def add_missing_columns(database, table, specifications):
    existing = table_columns(database, table)
    for column, declaration in specifications:
        if column not in existing:
            database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def migrate_character_columns(database):
    extend_legacy_score_range(database)
    specs = (("portrait_filename", "TEXT"), ("estus_available", "INTEGER NOT NULL DEFAULT 1"),
             ("class_path_id", "INTEGER REFERENCES class_path(id)"),
             ("racial_path_id", "INTEGER REFERENCES racial_path(id)"))
    add_missing_columns(database, "character", specs)


def extend_legacy_score_range(database):
    query = "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'character'"
    schema = database.execute(query).fetchone()["sql"]
    if "BETWEEN 8 AND 15" in schema:
        _extend_character_score_range(database)


ACTION_USE_SCHEMA = """
CREATE TABLE IF NOT EXISTS character_action_use (
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    path_type TEXT NOT NULL CHECK (path_type IN ('class', 'racial')),
    path_id INTEGER NOT NULL,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
    uses_spent INTEGER NOT NULL DEFAULT 0 CHECK (uses_spent >= 0),
    PRIMARY KEY (character_id, path_type, path_id, rank)
)"""


def migrate_removed_features(database):
    database.execute("DROP TABLE IF EXISTS change_log")
    database.execute("DROP TABLE IF EXISTS background")
    database.execute(ACTION_USE_SCHEMA)
    reset_legacy_character_fields(database)


def reset_legacy_character_fields(database):
    columns = table_columns(database, "character")
    for column in ("temporary_hp", "archived"):
        if column in columns:
            database.execute(f"UPDATE character SET {column} = 0")


SLOT_GROUPS = {
    "weapon": ("right_hand", "left_hand"), "shield": ("right_hand", "left_hand"),
    "tool": ("right_hand", "left_hand"), "armor": ("armor",),
    "accessory": ("ring_1", "ring_2", "ring_3", "ring_4"),
}


def migrate_equipment(database):
    text_fields = ("damage_dice", "damage_type", "uses", "stat", "effect", "slot", "icon_path")
    specs = tuple((field, "TEXT NOT NULL DEFAULT ''") for field in text_fields)
    add_missing_columns(database, "equipment", specs + (("stat_bonus", "INTEGER NOT NULL DEFAULT 0"),))
    assign_legacy_slots(database)
    reactivate_catalogues(database)


def assign_legacy_slots(database):
    query = "SELECT DISTINCT character_id FROM equipment WHERE equipped = 1 AND slot = ''"
    for row in database.execute(query).fetchall():
        assign_character_slots(database, row["character_id"])


def assign_character_slots(database, character_id):
    used = occupied_slots(database, character_id)
    for item in unslotted_items(database, character_id):
        assign_item_slot(database, item, used)


def occupied_slots(database, character_id):
    query = "SELECT slot FROM equipment WHERE character_id = ? AND equipped = 1 AND slot != ''"
    return {row["slot"] for row in database.execute(query, (character_id,)).fetchall()}


def unslotted_items(database, character_id):
    query = ("SELECT id, item_type FROM equipment WHERE character_id = ? "
             "AND equipped = 1 AND slot = '' ORDER BY id")
    return database.execute(query, (character_id,)).fetchall()


def assign_item_slot(database, item, used):
    slot = next((value for value in SLOT_GROUPS.get(item["item_type"], ()) if value not in used), None)
    database.execute("UPDATE equipment SET equipped = ?, slot = ? WHERE id = ?",
                     (1 if slot else 0, slot or "", item["id"]))
    if slot:
        used.add(slot)


def reactivate_catalogues(database):
    for table in ("player", "character_class", "species"):
        if "active" in table_columns(database, table):
            database.execute(f"UPDATE {table} SET active = 1")


def sync_game_config(database=None):
    database = database or get_db()
    if sync_ready(database):
        from dnd_manager.configuration.sync import synchronize
        synchronize(database, project_file("game_data.json"))
    return database


def sync_ready(database):
    return species_table_exists(database) and configured_catalogues_exist(database)


def species_table_exists(database):
    query = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'species'"
    return bool(database.execute(query).fetchone())


def configured_catalogues_exist(database):
    tables = ("species", "character_class")
    return all("configured" in table_columns(database, table) for table in tables)


@click.command("init-db")
def init_db_command():
    """Crée les tables de l'application."""
    init_db()
    click.echo("Base de données initialisée.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        migrate_installed_database(get_db())


def migrate_installed_database(database):
    query = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'character'"
    if database.execute(query).fetchone():
        _migrate_existing_database(database)
        sync_game_config(database)

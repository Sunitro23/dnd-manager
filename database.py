import json
import sqlite3
from pathlib import Path

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE_PATH"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db():
    schema_path = Path(__file__).with_name("schema.sql")
    database = get_db()
    database.executescript(schema_path.read_text(encoding="utf-8"))
    _migrate_existing_database(database)
    sync_game_config(database)


def table_columns(database, table):
    return {
        row["name"]
        for row in database.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _migrate_existing_database(database):
    class_columns = table_columns(database, "character_class")
    for field in (
        "strength",
        "dexterity",
        "constitution",
        "intelligence",
        "wisdom",
        "charisma",
    ):
        column = f"{field}_bonus"
        if column not in class_columns:
            database.execute(
                f"ALTER TABLE character_class ADD COLUMN {column} "
                "INTEGER NOT NULL DEFAULT 0"
            )
    if "configured" not in class_columns:
        database.execute(
            "ALTER TABLE character_class ADD COLUMN configured INTEGER NOT NULL DEFAULT 0"
        )

    species_columns = table_columns(database, "species")
    for column in (
        "physical_bonus",
        "elemental_bonus",
        "spiritual_bonus",
        "configured",
    ):
        if column not in species_columns:
            database.execute(
                f"ALTER TABLE species ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
            )

    character_columns = table_columns(database, "character")
    if "portrait_filename" not in character_columns:
        database.execute("ALTER TABLE character ADD COLUMN portrait_filename TEXT")
    if "estus_available" not in character_columns:
        database.execute(
            "ALTER TABLE character ADD COLUMN estus_available "
            "INTEGER NOT NULL DEFAULT 1"
        )
    for column, target in (
        ("class_path_id", "class_path"),
        ("racial_path_id", "racial_path"),
    ):
        if column not in character_columns:
            database.execute(
                f"ALTER TABLE character ADD COLUMN {column} INTEGER REFERENCES {target}(id)"
            )

    database.execute("DROP TABLE IF EXISTS change_log")
    database.execute("DROP TABLE IF EXISTS background")
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS character_action_use (
            character_id INTEGER NOT NULL
                REFERENCES character(id) ON DELETE CASCADE,
            path_type TEXT NOT NULL
                CHECK (path_type IN ('class', 'racial')),
            path_id INTEGER NOT NULL,
            rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
            uses_spent INTEGER NOT NULL DEFAULT 0 CHECK (uses_spent >= 0),
            PRIMARY KEY (character_id, path_type, path_id, rank)
        )
        """
    )

    if "temporary_hp" in character_columns:
        database.execute("UPDATE character SET temporary_hp = 0")
    if "archived" in character_columns:
        database.execute("UPDATE character SET archived = 0")

    equipment_columns = table_columns(database, "equipment")
    for column in ("damage_dice", "damage_type", "uses", "stat", "effect"):
        if column not in equipment_columns:
            database.execute(
                f"ALTER TABLE equipment ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
            )
    if "stat_bonus" not in equipment_columns:
        database.execute(
            "ALTER TABLE equipment ADD COLUMN stat_bonus INTEGER NOT NULL DEFAULT 0"
        )
    if "slot" not in equipment_columns:
        database.execute(
            "ALTER TABLE equipment ADD COLUMN slot TEXT NOT NULL DEFAULT ''"
        )
    if "icon_path" not in equipment_columns:
        database.execute(
            "ALTER TABLE equipment ADD COLUMN icon_path TEXT NOT NULL DEFAULT ''"
        )
    slot_groups = {
        "weapon": ("right_hand", "left_hand"),
        "shield": ("right_hand", "left_hand"),
        "tool": ("right_hand", "left_hand"),
        "armor": ("armor",),
        "accessory": ("ring_1", "ring_2", "ring_3", "ring_4"),
    }
    character_ids = database.execute(
        """
        SELECT DISTINCT character_id FROM equipment
        WHERE equipped = 1 AND slot = ''
        """
    ).fetchall()
    for character_row in character_ids:
        used_slots = {
            row["slot"]
            for row in database.execute(
                """
                SELECT slot FROM equipment
                WHERE character_id = ? AND equipped = 1 AND slot != ''
                """,
                (character_row["character_id"],),
            ).fetchall()
        }
        items = database.execute(
            """
            SELECT id, item_type FROM equipment
            WHERE character_id = ? AND equipped = 1 AND slot = ''
            ORDER BY id
            """,
            (character_row["character_id"],),
        ).fetchall()
        for item in items:
            slot = next(
                (
                    candidate
                    for candidate in slot_groups.get(item["item_type"], ())
                    if candidate not in used_slots
                ),
                None,
            )
            database.execute(
                "UPDATE equipment SET equipped = ?, slot = ? WHERE id = ?",
                (1 if slot else 0, slot or "", item["id"]),
            )
            if slot:
                used_slots.add(slot)

    for table in ("player", "character_class", "species"):
        if "active" in table_columns(database, table):
            database.execute(f"UPDATE {table} SET active = 1")

    database.commit()


ABILITY_ABBREVIATIONS = {
    "FOR": "strength",
    "DEX": "dexterity",
    "CON": "constitution",
    "INT": "intelligence",
    "SAG": "wisdom",
    "CHA": "charisma",
}


def racial_ability_bonuses(text):
    bonuses = {f"{field}_bonus": 0 for field in ABILITY_ABBREVIATIONS.values()}
    for part in text.split(","):
        value, abbreviation = part.strip().split()
        bonuses[f"{ABILITY_ABBREVIATIONS[abbreviation]}_bonus"] = int(value)
    return bonuses


def sync_game_config(database=None):
    database = database or get_db()
    if not database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'species'"
    ).fetchone():
        return
    if (
        "configured" not in table_columns(database, "species")
        or "configured" not in table_columns(database, "character_class")
    ):
        return

    config_path = Path(__file__).with_name("game_data.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    database.execute("UPDATE character_class SET configured = 0")
    database.execute("UPDATE species SET configured = 0")
    database.execute("UPDATE class_path SET configured = 0")
    database.execute("UPDATE racial_path SET configured = 0")

    for item in config["classes"]:
        database.execute(
            """
            INSERT INTO character_class (stable_key, name, hit_die, configured)
            VALUES (:stable_key, :name, :hit_die, 1)
            ON CONFLICT DO UPDATE SET
                hit_die = excluded.hit_die,
                strength_bonus = 0,
                dexterity_bonus = 0,
                constitution_bonus = 0,
                intelligence_bonus = 0,
                wisdom_bonus = 0,
                charisma_bonus = 0,
                configured = 1
            """,
            {
                **item,
                "stable_key": item["name"].casefold().replace(" ", "-"),
            },
        )
        class_id = database.execute(
            "SELECT id FROM character_class WHERE name = ?", (item["name"],)
        ).fetchone()["id"]
        for path in item["paths"]:
            database.execute(
                """
                INSERT INTO class_path
                    (class_id, name, abilities, ranks_json, configured)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(class_id, name) DO UPDATE SET
                    abilities = excluded.abilities,
                    ranks_json = excluded.ranks_json,
                    configured = 1
                """,
                (
                    class_id,
                    path["name"],
                    path["abilities"],
                    json.dumps(path["ranks"], ensure_ascii=False),
                ),
            )

    chevalier = database.execute(
        "SELECT id FROM character_class WHERE name = 'Chevalier' AND configured = 1"
    ).fetchone()
    if chevalier:
        database.execute(
            """
            UPDATE character
            SET class_id = ?, class_path_id = NULL
            WHERE class_id IN (
                SELECT id FROM character_class
                WHERE name = 'Barbare' AND configured = 0
            )
            """,
            (chevalier["id"],),
        )

    for item in config["races"]:
        defenses = item["defenses"]
        database.execute(
            """
            INSERT INTO species (
                name, description, traits,
                physical_bonus, elemental_bonus, spiritual_bonus, configured
            )
            VALUES (:name, '', :particularity, :physical, :elemental, :spiritual, 1)
            ON CONFLICT DO UPDATE SET
                description = excluded.description,
                traits = excluded.traits,
                physical_bonus = excluded.physical_bonus,
                elemental_bonus = excluded.elemental_bonus,
                spiritual_bonus = excluded.spiritual_bonus,
                configured = 1
            """,
            {**item, **defenses},
        )
        species_id = database.execute(
            "SELECT id FROM species WHERE name = ?", (item["name"],)
        ).fetchone()["id"]
        for path in item["paths"]:
            bonuses = racial_ability_bonuses(path["abilities"])
            database.execute(
                """
                INSERT INTO racial_path (
                    species_id, name, abilities, ranks_json,
                    strength_bonus, dexterity_bonus, constitution_bonus,
                    intelligence_bonus, wisdom_bonus, charisma_bonus, configured
                )
                VALUES (
                    :species_id, :name, :abilities, :ranks_json,
                    :strength_bonus, :dexterity_bonus, :constitution_bonus,
                    :intelligence_bonus, :wisdom_bonus, :charisma_bonus, 1
                )
                ON CONFLICT(species_id, name) DO UPDATE SET
                    abilities = excluded.abilities,
                    ranks_json = excluded.ranks_json,
                    strength_bonus = excluded.strength_bonus,
                    dexterity_bonus = excluded.dexterity_bonus,
                    constitution_bonus = excluded.constitution_bonus,
                    intelligence_bonus = excluded.intelligence_bonus,
                    wisdom_bonus = excluded.wisdom_bonus,
                    charisma_bonus = excluded.charisma_bonus,
                    configured = 1
                """,
                {
                    "species_id": species_id,
                    "name": path["name"],
                    "abilities": path["abilities"],
                    "ranks_json": json.dumps(path["ranks"], ensure_ascii=False),
                    **bonuses,
                },
            )

    from rules import adjusted_current_hp, maximum_hp

    database.execute(
        """
        UPDATE character
        SET racial_path_id = NULL
        WHERE racial_path_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM character_rank cr
              WHERE cr.character_id = character.id
                AND cr.path_type = 'racial'
                AND cr.path_id = character.racial_path_id
                AND cr.rank = 1
          )
        """
    )
    characters = database.execute(
        """
        SELECT c.id, c.level, c.constitution, c.current_hp, c.max_hp,
               cc.hit_die,
               cc.constitution_bonus AS class_constitution_bonus,
               COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus
        FROM character c
        JOIN character_class cc ON cc.id = c.class_id
        LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
        """
    ).fetchall()
    for character in characters:
        new_max_hp = maximum_hp(
            character["hit_die"],
            character["level"],
            character["constitution"]
            + character["class_constitution_bonus"]
            + character["racial_constitution_bonus"],
        )
        database.execute(
            "UPDATE character SET current_hp = ?, max_hp = ? WHERE id = ?",
            (
                adjusted_current_hp(
                    character["current_hp"], character["max_hp"], new_max_hp
                ),
                new_max_hp,
                character["id"],
            ),
        )
    database.commit()


@click.command("init-db")
def init_db_command():
    """Crée les tables de l'application."""
    init_db()
    click.echo("Base de données initialisée.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        database = get_db()
        if database.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'character'"
        ).fetchone():
            _migrate_existing_database(database)
            sync_game_config(database)

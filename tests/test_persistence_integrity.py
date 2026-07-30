"""Non-régressions sur les écritures qui traversent un redémarrage ou un clonage.

Ces deux chemins recalculaient les PV avec une formule incomplète et recopiaient un
sous-ensemble des colonnes d'équipement, produisant des pertes de données silencieuses.
"""

import tempfile
import unittest
from pathlib import Path

from app import create_app
from dnd_manager.infrastructure.database import get_db, init_db

CREATE_CHARACTER_SQL = """
INSERT INTO character (
    name, character_type, class_id, species_id, level,
    strength, dexterity, constitution, intelligence, wisdom, charisma,
    current_hp, max_hp
) VALUES (?, 'player', ?, ?, ?, 8, 8, 14, 8, 8, 8, 1, 1)
"""
CREATE_RING_SQL = """
INSERT INTO equipment (character_id, name, item_type, equipped, slot, stat, stat_bonus)
VALUES (?, 'Anneau de vie', 'accessory', 1, 'ring_1', 'CON', 2)
"""
CREATE_SWORD_SQL = """
INSERT INTO equipment (
    character_id, name, item_type, equipped, slot, damage_dice, damage_type,
    icon_path, uses, effect, notes, physical_bonus
) VALUES (?, 'Épée longue', 'weapon', 1, 'right_hand', '2d6', 'physical',
          '01_weapons/lame.png', '', 'Tranchant', 'Héritage familial', 0)
"""


class PersistenceIntegrityTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "integrity.sqlite3"
        self.app = self.build_app()
        with self.app.app_context():
            init_db()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def build_app(self):
        return create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_PATH": str(self.database_path),
            "PORTRAIT_PATH": str(Path(self.temporary_directory.name) / "portraits"),
        })

    def catalogue_identifiers(self, database):
        class_row = database.execute(
            "SELECT id FROM character_class WHERE configured = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        species_row = database.execute(
            "SELECT id FROM species WHERE configured = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        return class_row["id"], species_row["id"]

    def create_character(self, database, name="Aldren", level=3):
        class_id, species_id = self.catalogue_identifiers(database)
        database.execute(CREATE_CHARACTER_SQL, (name, class_id, species_id, level))
        return database.execute(
            "SELECT id FROM character WHERE name = ?", (name,)
        ).fetchone()["id"]

    def health_of(self, database, character_id):
        return database.execute(
            "SELECT current_hp, max_hp, version FROM character WHERE id = ?",
            (character_id,),
        ).fetchone()

    def test_restart_preserves_health_granted_by_a_constitution_accessory(self):
        from dnd_manager.characters.inventory.item_form import recalculate_hp

        with self.app.app_context():
            database = get_db()
            character_id = self.create_character(database)
            database.execute(CREATE_RING_SQL, (character_id,))
            recalculate_hp(database, character_id)
            database.commit()
            before = self.health_of(database, character_id)

        with self.build_app().app_context():
            after = self.health_of(get_db(), character_id)

        self.assertEqual((after["current_hp"], after["max_hp"]),
                         (before["current_hp"], before["max_hp"]))

    def test_restart_does_not_bump_version_when_health_is_unchanged(self):
        with self.app.app_context():
            database = get_db()
            character_id = self.create_character(database)
            database.commit()

        with self.build_app().app_context():
            first = self.health_of(get_db(), character_id)
        with self.build_app().app_context():
            second = self.health_of(get_db(), character_id)

        self.assertEqual(first["version"], second["version"])

    def test_restart_bumps_version_when_it_rewrites_health(self):
        with self.app.app_context():
            database = get_db()
            character_id = self.create_character(database)
            database.execute("UPDATE character SET max_hp = 999, current_hp = 999 WHERE id = ?",
                             (character_id,))
            database.commit()
            before = self.health_of(database, character_id)

        with self.build_app().app_context():
            after = self.health_of(get_db(), character_id)

        self.assertNotEqual(after["max_hp"], before["max_hp"])
        self.assertEqual(after["version"], before["version"] + 1)

    def test_duplicated_character_keeps_every_equipment_column(self):
        from dnd_manager.characters.administration.http import duplicate_character

        with self.app.app_context():
            database = get_db()
            character_id = self.create_character(database, level=1)
            database.execute(CREATE_SWORD_SQL, (character_id,))
            database.commit()
            copy_id = duplicate_character(database, character_id, "Aldren — copie")
            columns = ("name, item_type, equipped, slot, damage_dice, damage_type, "
                       "icon_path, uses, effect, notes")
            source = dict(database.execute(
                f"SELECT {columns} FROM equipment WHERE character_id = ?",
                (character_id,)).fetchone())
            copy = dict(database.execute(
                f"SELECT {columns} FROM equipment WHERE character_id = ?",
                (copy_id,)).fetchone())

        self.assertEqual(copy, source)

    def test_duplicated_character_never_equips_an_item_without_a_slot(self):
        from dnd_manager.characters.administration.http import duplicate_character

        with self.app.app_context():
            database = get_db()
            character_id = self.create_character(database, level=1)
            database.execute(CREATE_SWORD_SQL, (character_id,))
            database.execute(CREATE_RING_SQL, (character_id,))
            database.commit()
            copy_id = duplicate_character(database, character_id, "Aldren — copie")
            orphans = database.execute(
                "SELECT COUNT(*) FROM equipment WHERE character_id = ? "
                "AND equipped = 1 AND slot = ''", (copy_id,)).fetchone()[0]

        self.assertEqual(orphans, 0)

    def test_duplicated_character_health_matches_its_copied_accessories(self):
        from dnd_manager.characters.administration.http import duplicate_character

        with self.app.app_context():
            database = get_db()
            character_id = self.create_character(database, level=1)
            database.execute(CREATE_RING_SQL, (character_id,))
            database.execute("UPDATE character SET current_hp = 3, max_hp = 3 WHERE id = ?",
                             (character_id,))
            database.commit()
            copy_id = duplicate_character(database, character_id, "Aldren — copie")
            copy = self.health_of(database, copy_id)

        # d10 + modificateur de (14 + 2) = 10 + 3
        self.assertEqual((copy["current_hp"], copy["max_hp"]), (13, 13))


if __name__ == "__main__":
    unittest.main()

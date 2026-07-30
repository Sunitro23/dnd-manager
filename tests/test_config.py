import tempfile
import unittest
import json
from pathlib import Path

from app import create_app
from dnd_manager.infrastructure.database import get_db, init_db, sync_game_config


class GameConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_PATH": str(
                    Path(self.temporary_directory.name) / "seed.sqlite3"
                ),
            }
        )
        with self.app.app_context():
            init_db()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_game_config_installs_classes_races_and_paths(self):
        with self.app.app_context():
            database = get_db()
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM character_class").fetchone()[0],
                7,
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM species").fetchone()[0],
                12,
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM class_path").fetchone()[0],
                14,
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM racial_path").fetchone()[0],
                24,
            )

    def test_game_config_sync_is_idempotent(self):
        with self.app.app_context():
            database = get_db()
            sync_game_config(database)
            sync_game_config(database)
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM character_class").fetchone()[0],
                7,
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM species").fetchone()[0],
                12,
            )

    def test_soulborn_origins_keep_distinct_defenses(self):
        with self.app.app_context():
            database = get_db()
            rows = database.execute(
                "SELECT name, physical_bonus, elemental_bonus, spiritual_bonus "
                "FROM racial_path WHERE name IN ('Enfant de la Mort', 'Enfant des Abysses') "
                "ORDER BY name"
            ).fetchall()
            values = {row["name"]: tuple(row[key] for key in (
                "physical_bonus", "elemental_bonus", "spiritual_bonus")) for row in rows}
            self.assertEqual(values["Enfant de la Mort"], (-2, 0, 2))
            self.assertEqual(values["Enfant des Abysses"], (0, -2, 3))

    def test_murkmans_are_not_installed(self):
        with self.app.app_context():
            database = get_db()
            row = database.execute(
                "SELECT 1 FROM species WHERE stable_key = 'species.murkmans'"
            ).fetchone()
            self.assertIsNone(row)

    def test_game_config_has_stable_ids_and_structured_resources(self):
        config = json.loads(Path("game_data.json").read_text(encoding="utf-8"))
        chevalier = config["classes"][0]
        interposition = chevalier["paths"][0]["ranks"][1]
        self.assertEqual(config["schema_version"], "2.0.0")
        self.assertEqual(chevalier["id"], "class.chevalier")
        self.assertEqual(interposition["active"]["resource"]["maximum"], 3)

    def test_bonfire_resources_use_canonical_long_rest(self):
        config = json.loads(Path("game_data.json").read_text(encoding="utf-8"))
        resources = (rank["active"].get("resource")
                     for group in ("classes", "races")
                     for option in config[group]
                     for path in option["paths"]
                     for rank in path["ranks"] if rank.get("active"))
        recoveries = {value for resource in resources if resource
                      for value in resource["recovery"]}
        self.assertNotIn("bonfire_rest", recoveries)
        self.assertIn("long_rest", recoveries)


if __name__ == "__main__":
    unittest.main()

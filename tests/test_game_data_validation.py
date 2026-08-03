import tempfile
import unittest
from pathlib import Path

from app import create_app
from dnd_manager.infrastructure.database import get_db, init_db
from dnd_manager.paths.repository import find_path
from dnd_manager.paths.normalized import capability_description
from dnd_manager.ruleset.sqlite_catalog import SqliteRulesetCatalog


class CatalogueDatabaseValidationTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_PATH": str(Path(self.temporary_directory.name) / "catalogue.sqlite3"),
        })

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_sql_seed_installs_the_complete_catalogue(self):
        with self.app.app_context():
            init_db()
            database = get_db()
            self.assertEqual(database.execute(
                "SELECT COUNT(*) FROM path_definition WHERE status='published'"
            ).fetchone()[0], 38)
            self.assertEqual(database.execute(
                "SELECT COUNT(*) FROM path_rank_definition"
            ).fetchone()[0], 194)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM path_rank").fetchone()[0], 190)
            self.assertEqual(database.execute(
                "SELECT COUNT(*) FROM path_capability"
            ).fetchone()[0], 194)

    def test_ruleset_is_built_from_sqlite(self):
        with self.app.app_context():
            init_db()
            bundle = SqliteRulesetCatalog(get_db()).current()
            self.assertEqual(len(bundle["features"]), 194)
            self.assertEqual(bundle["coverage"]["full"], 4)
            self.assertEqual(bundle["coverage"]["partial"], 4)
            self.assertEqual(bundle["coverage"]["none"], 186)
            self.assertRegex(bundle["revision"], r"^sha256:[a-f0-9]{64}$")

    def test_chevalier_descriptions_are_structured_and_clear(self):
        with self.app.app_context():
            init_db()
            database = get_db()
            berserker = find_path(database, "class", 2)
            rempart = find_path(database, "class", 1)
            self.assertIn("réduit toutes ses Défenses de 2", berserker["ranks"][0]["active"]["effect"])
            self.assertNotIn("Défenses de 2.0", berserker["ranks"][0]["active"]["effect"])
            self.assertIn("reste à au moins 1 PV", berserker["ranks"][2]["active"]["effect"])
            self.assertIn("perd 1d8 PV par tour", berserker["ranks"][4]["active"]["effect"])
            self.assertNotIn("récupérée après", berserker["ranks"][4]["active"]["effect"])
            self.assertIn("augmentent toutes leurs Défenses de +1", rempart["ranks"][2]["active"]["effect"])
            self.assertIn("cet allié n’en subit que la moitié", rempart["ranks"][4]["active"]["effect"])

    def test_hybrid_description_keeps_generated_effects_and_manual_details(self):
        description = capability_description(
            "hybrid", "Le personnage réduit les dégâts reçus de 1d8.",
            "Il doit porter un bouclier.",
        )
        self.assertEqual(
            description,
            "Le personnage réduit les dégâts reçus de 1d8. Il doit porter un bouclier.",
        )


if __name__ == "__main__":
    unittest.main()

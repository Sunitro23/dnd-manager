import tempfile
import unittest
import json
from pathlib import Path

from app import create_app
from dnd_manager.infrastructure.database import get_db, init_db
from dnd_manager.infrastructure.database import migrate_removed_path_fields
from dnd_manager.paths.repository import find_path
from dnd_manager.paths.json_catalog import synchronize_catalog
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

    def test_action_capabilities_are_activated_by_the_player(self):
        with self.app.app_context():
            init_db()
            database = get_db()
            names = ("Flamme noire", "Piège incendiaire", "Blizzard blanc", "Ordre impérieux")
            placeholders = ",".join("?" for _name in names)
            rows = database.execute(
                f"SELECT name,execution_mode,action_cost,trigger_event FROM path_capability "
                f"WHERE name IN ({placeholders})", names,
            ).fetchall()
            self.assertEqual({row["name"] for row in rows}, set(names))
            for row in rows:
                self.assertEqual(row["execution_mode"], "activated")
                self.assertIsNone(row["trigger_event"])
                self.assertNotEqual(row["action_cost"], "none")

    def test_json_catalog_is_authoritative(self):
        with self.app.app_context():
            init_db()
            filename = Path(self.app.config["PATH_CATALOG_JSON"])
            payload = json.loads(filename.read_text(encoding="utf-8"))
            payload["classes"][0]["name"] = "Classe modifiée en JSON"
            removed_path = payload["voies"].pop()
            payload["voies"].append({
                "stable_key": "path.test.guide-debutant", "type": "class",
                "origine": payload["classes"][0]["stable_key"],
                "name": "Voie créée en JSON", "abilities": "FOR",
                "status": "draft", "rangs": [],
            })
            filename.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

            synchronize_catalog(get_db(), filename)

            row = get_db().execute(
                "SELECT name FROM character_class WHERE stable_key=?",
                (payload["classes"][0]["stable_key"],),
            ).fetchone()
            self.assertEqual(row["name"], "Classe modifiée en JSON")
            created = get_db().execute(
                "SELECT status FROM path_definition WHERE stable_key='path.test.guide-debutant'"
            ).fetchone()
            self.assertEqual(created["status"], "draft")
            removed = get_db().execute(
                "SELECT 1 FROM path_definition WHERE stable_key=?",
                (removed_path["stable_key"],),
            ).fetchone()
            self.assertIsNone(removed)

    def test_json_catalog_recovers_legacy_origins_without_stable_keys(self):
        with self.app.app_context():
            init_db()
            database = get_db()
            database.execute(
                "UPDATE character_class SET stable_key='' WHERE name='Chevalier'"
            )
            database.execute(
                "UPDATE species SET stable_key='' WHERE name='Humains'"
            )
            database.commit()

            synchronize_catalog(database, self.app.config["PATH_CATALOG_JSON"])

            self.assertIsNotNone(database.execute(
                "SELECT 1 FROM character_class WHERE stable_key='class.chevalier'"
            ).fetchone())
            self.assertIsNotNone(database.execute(
                "SELECT 1 FROM species WHERE stable_key='species.humains'"
            ).fetchone())
            self.assertEqual(database.execute(
                "SELECT COUNT(*) FROM path_definition WHERE status='published'"
            ).fetchone()[0], 38)

    def test_removed_path_text_fields_are_migrated_to_manual_effects(self):
        with self.app.app_context():
            init_db()
            database = get_db()
            database.execute(
                "ALTER TABLE path_capability ADD COLUMN structure_level TEXT NOT NULL "
                "DEFAULT 'structured'"
            )
            database.execute(
                "ALTER TABLE path_capability ADD COLUMN manual_description TEXT NOT NULL DEFAULT ''"
            )
            database.execute(
                "ALTER TABLE path_rank ADD COLUMN unlock_note TEXT NOT NULL DEFAULT ''"
            )
            capability = database.execute(
                "SELECT pc.id,pc.path_rank_id FROM path_capability pc ORDER BY pc.id LIMIT 1"
            ).fetchone()
            database.execute(
                "UPDATE path_capability SET manual_description='Ancienne précision.' WHERE id=?",
                (capability["id"],),
            )
            database.execute(
                "UPDATE path_rank SET unlock_note='Ancienne règle du rang.' WHERE id=?",
                (capability["path_rank_id"],),
            )

            migrate_removed_path_fields(database)

            capability_columns = {row["name"] for row in database.execute(
                "PRAGMA table_info(path_capability)"
            ).fetchall()}
            rank_columns = {row["name"] for row in database.execute(
                "PRAGMA table_info(path_rank)"
            ).fetchall()}
            self.assertFalse({"structure_level", "manual_description"} & capability_columns)
            self.assertNotIn("unlock_note", rank_columns)
            labels = {row["label"] for row in database.execute(
                "SELECT label FROM effect_node WHERE capability_id=? AND node_type='manual_effect'",
                (capability["id"],),
            ).fetchall()}
            self.assertIn("Ancienne précision.", labels)
            self.assertIn("Ancienne règle du rang.", labels)

if __name__ == "__main__":
    unittest.main()

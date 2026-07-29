import tempfile
import unittest
from pathlib import Path

from app import create_app
from database import get_db, init_db, sync_game_config


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
                14,
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM class_path").fetchone()[0],
                14,
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM racial_path").fetchone()[0],
                28,
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
                14,
            )


if __name__ == "__main__":
    unittest.main()

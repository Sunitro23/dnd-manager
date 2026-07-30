"""Cohérence entre l'API d'échange et les règles de visibilité de l'interface web.

L'API listait et modifiait les fiches réservées au MJ, que l'interface masque.
"""

import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from dnd_manager.infrastructure.database import get_db, init_db

CREATE_CHARACTER_SQL = """
INSERT INTO character (
    name, character_type, visibility, class_id, species_id, level,
    strength, dexterity, constitution, intelligence, wisdom, charisma,
    current_hp, max_hp
) VALUES (?, 'player', ?, ?, ?, 10, 8, 8, 14, 8, 8, 8, 50, 50)
"""
API_TOKEN = "combat-bridge-token"


class CharacterApiAccessTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "GM_PASSWORD_HASH": generate_password_hash("dragon"),
            "API_TOKEN": API_TOKEN,
            "API_PUBLIC": True,
            "DATABASE_PATH": str(Path(self.temporary_directory.name) / "api.sqlite3"),
            "PORTRAIT_PATH": str(Path(self.temporary_directory.name) / "portraits"),
        })
        with self.app.app_context():
            init_db()
            self.public_id, self.secret_id = self.create_characters()
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def create_characters(self):
        database = get_db()
        class_id = database.execute(
            "SELECT id FROM character_class WHERE configured = 1 ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        species_id = database.execute(
            "SELECT id FROM species WHERE configured = 1 ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        identifiers = tuple(
            self.insert_character(database, name, visibility, class_id, species_id)
            for name, visibility in (("Héros", "campaign"), ("Boss secret", "gm"))
        )
        database.commit()
        return identifiers

    def insert_character(self, database, name, visibility, class_id, species_id):
        database.execute(CREATE_CHARACTER_SQL, (name, visibility, class_id, species_id))
        return database.execute(
            "SELECT id FROM character WHERE name = ?", (name,)).fetchone()["id"]

    def token_headers(self):
        return {"Authorization": f"Bearer {API_TOKEN}"}

    def test_public_client_only_lists_campaign_characters(self):
        response = self.client.get("/api/v1/characters")
        names = [character["name"] for character in response.json["characters"]]
        self.assertEqual(names, ["Héros"])

    def test_public_client_cannot_read_a_gm_only_character(self):
        response = self.client.get(f"/api/v1/characters/{self.secret_id}")
        self.assertEqual(response.status_code, 404)

    def test_public_client_cannot_read_a_gm_only_combat_profile(self):
        response = self.client.get(f"/api/v1/characters/{self.secret_id}/combat-profile")
        self.assertEqual(response.status_code, 404)

    def test_public_client_cannot_write_health_of_a_gm_only_character(self):
        response = self.client.put(f"/api/v1/characters/{self.secret_id}/health",
                                   json={"current_hp": 1, "expected_version": 1})
        self.assertEqual(response.status_code, 404)

    def test_public_client_still_reads_campaign_characters(self):
        response = self.client.get(f"/api/v1/characters/{self.public_id}")
        self.assertEqual((response.status_code, response.json["name"]), (200, "Héros"))

    def test_token_holder_reads_gm_only_characters(self):
        response = self.client.get(f"/api/v1/characters/{self.secret_id}",
                                   headers=self.token_headers())
        self.assertEqual((response.status_code, response.json["name"]), (200, "Boss secret"))

    def test_token_holder_lists_every_character(self):
        response = self.client.get("/api/v1/characters", headers=self.token_headers())
        names = sorted(character["name"] for character in response.json["characters"])
        self.assertEqual(names, ["Boss secret", "Héros"])

    def test_snapshot_reads_each_path_definition_once(self):
        with self.app.app_context():
            database = get_db()
            self.unlock_five_ranks(database, self.public_id)
            counter = CountingConnection(database)
            from dnd_manager.character_api.sqlite_repository import (
                SqliteCharacterExchangeRepository,
            )

            snapshot = SqliteCharacterExchangeRepository(counter).find(self.public_id)

        self.assertEqual(len(snapshot.feature_ids), 5)
        # 1 fiche + 1 accessoires + 1 défenses + 1 équipement + 1 rangs + 1 voie = 6
        self.assertLessEqual(counter.queries, 8)

    def unlock_five_ranks(self, database, character_id):
        class_id = database.execute(
            "SELECT class_id FROM character WHERE id = ?", (character_id,)).fetchone()["class_id"]
        path_id = database.execute(
            "SELECT id FROM class_path WHERE class_id = ? AND configured = 1 ORDER BY id LIMIT 1",
            (class_id,)).fetchone()["id"]
        for rank in range(1, 6):
            database.execute(
                "INSERT INTO character_rank (character_id, path_type, path_id, rank) "
                "VALUES (?, 'class', ?, ?)", (character_id, path_id, rank))
        database.commit()


class CountingConnection:
    """Compte les requêtes sans modifier la connexion (dont `execute` est en lecture seule)."""

    def __init__(self, database):
        self.database = database
        self.queries = 0

    def execute(self, *arguments, **keywords):
        self.queries += 1
        return self.database.execute(*arguments, **keywords)

    def __getattr__(self, name):
        return getattr(self.database, name)


if __name__ == "__main__":
    unittest.main()

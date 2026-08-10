import io
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app
from dnd_manager.infrastructure.database import init_db


class ApplicationTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "test.sqlite3"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "GM_PASSWORD_HASH": generate_password_hash("dragon"),
                "API_TOKEN": "combat-bridge-token",
                "API_PUBLIC": False,
                "DATABASE_PATH": str(database_path),
                "PORTRAIT_PATH": str(Path(self.temporary_directory.name) / "portraits"),
            }
        )
        with self.app.app_context():
            init_db()
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    @contextmanager
    def silenced_logger(self):
        """Les incidents attendus sont journalisés : éviter le bruit dans la sortie."""
        self.app.logger.disabled = True
        try:
            yield
        finally:
            self.app.logger.disabled = False

    def csrf_token(self):
        self.client.get("/mj/connexion")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def login(self):
        return self.client.post(
            "/mj/connexion",
            data={"password": "dragon", "csrf_token": self.csrf_token()},
            follow_redirects=True,
        )

    def path_form(self, path_type="class", owner_id=1, name="Voie des braises"):
        values = {
            "csrf_token": self.csrf_token(), "path_type": path_type,
            "class_id" if path_type == "class" else "species_id": str(owner_id),
            "name": name,
            "abilities": "FOR, CON" if path_type == "class" else "+1 FOR, +1 SAG",
        }
        for rank in range(1, 6):
            values.update({
                f"rank_{rank}_name": f"Braise {rank}",
                f"rank_{rank}_mode": "active" if rank == 1 else "passive",
                f"rank_{rank}_effect": f"Effet du rang {rank}.",
                f"rank_{rank}_timing": "Action", f"rank_{rank}_uses": "1/combat",
                f"rank_{rank}_frequency": "Permanent",
            })
        return values

    def create_catalogues(self):
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            class_id = database.execute(
                """
                INSERT INTO character_class
                    (stable_key, name, description, hit_die)
                VALUES ('gardien', 'Gardien', '', 10)
                """
            ).lastrowid
            species_id = database.execute(
                """
                INSERT INTO species (stable_key, name, description, traits, size, speed)
                VALUES (
                    'species.humain',
                    'Humain',
                    'Une espèce polyvalente.',
                    'Débrouillardise, compétence supplémentaire, polyvalence.',
                    'Moyenne',
                    30
                )
                """
            ).lastrowid
            database.commit()
            return class_id, species_id

    def character_form(self, class_id, species_id, **overrides):
        values = {
            "csrf_token": self.csrf_token(),
            "name": "Aldren",
            "owner_name": "Lise",
            "class_id": str(class_id),
            "species_id": str(species_id),
            "strength": "15",
            "dexterity": "10",
            "constitution": "15",
            "intelligence": "10",
            "wisdom": "13",
            "charisma": "8",
            "description": "Protecteur du groupe",
            "personal_info": "Toujours calme",
        }
        values.update(overrides)
        return values

    def create_public_character(self, **overrides):
        class_id, species_id = self.create_catalogues()
        self.client.post(
            "/personnages/nouveau",
            data=self.character_form(class_id, species_id, **overrides),
        )
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            return get_db().execute(
                "SELECT id FROM character ORDER BY id DESC LIMIT 1"
            ).fetchone()["id"]

    def admin_character_form(self, **overrides):
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character = get_db().execute(
                """
                SELECT species_id, racial_path_id
                FROM character
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        values = {
            "csrf_token": self.csrf_token(),
            "name": "Aldren",
            "owner_name": "Lise",
            "character_type": "player",
            "visibility": "campaign",
            "level": "1",
            "species_id": str(character["species_id"]),
            "racial_path_id": (
                str(character["racial_path_id"]) if character["racial_path_id"] else ""
            ),
            "strength": "15",
            "dexterity": "10",
            "constitution": "15",
            "intelligence": "10",
            "wisdom": "13",
            "charisma": "8",
        }
        values.update(overrides)
        return values

    def test_public_campaign_is_available(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Choisir un personnage", response.get_data(as_text=True))

    def test_character_api_requires_a_bearer_token(self):
        response = self.client.get("/api/v1/characters/1")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"]["status"], 401)

    def test_character_api_can_run_publicly_with_cors(self):
        self.app.config["API_PUBLIC"] = True
        response = self.client.get("/api/v1/", headers={"Origin": "http://localhost:5173"})
        self.assertEqual((response.status_code, response.json["public"]), (200, True))
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(self.client.get("/api/v1/characters").status_code, 200)

    def test_character_api_exposes_its_openapi_contract(self):
        self.app.config["API_PUBLIC"] = True
        response = self.client.get("/api/v1/openapi.yaml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("openapi: 3.1.0", response.get_data(as_text=True))
        response.close()

    def test_character_api_can_restrict_cors_to_one_origin(self):
        self.app.config.update(API_PUBLIC=True, API_CORS_ORIGIN="https://engine.test")
        allowed = self.client.get("/api/v1/", headers={"Origin": "https://engine.test"})
        rejected = self.client.get("/api/v1/", headers={"Origin": "https://other.test"})
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"],
                         "https://engine.test")
        self.assertNotIn("Access-Control-Allow-Origin", rejected.headers)

    def test_character_api_exposes_a_stable_snapshot(self):
        character_id = self.create_public_character()
        response = self.api_get(f"/api/v1/characters/{character_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["name"], "Aldren")
        self.assertEqual(response.json["abilities"][0], {
            "key": "strength", "modifier": 2, "score": 15})
        self.assertEqual(response.json["class_id"], "gardien")
        self.assertEqual(response.json["species_id"], "species.humain")
        self.assertIsNone(response.json["class_path_id"])
        self.assertIsNone(response.json["racial_path_id"])
        self.assertEqual((response.json["size"], response.json["speed"]), ("Moyenne", 30))
        self.assertEqual([item["key"] for item in response.json["base_defenses"]],
                         ["physical", "elemental", "spiritual"])
        self.assertEqual(response.json["equipment"], [])
        self.assertIn("feature_ids", response.json)
        self.assertIn("resources", response.json)
        self.assertRegex(response.json["ruleset_revision"], r"^sha256:[a-f0-9]{64}$")
        self.assertEqual(response.headers["ETag"], '"1"')

    def test_character_api_supports_conditional_snapshot_reads(self):
        character_id = self.create_public_character()
        response = self.api_get(f"/api/v1/characters/{character_id}")
        cached = self.client.get(
            f"/api/v1/characters/{character_id}",
            headers=self.api_headers() | {"If-None-Match": response.headers["ETag"]})
        self.assertEqual(cached.status_code, 304)

    def test_combat_profile_only_contains_unlocked_features(self):
        character_id = self.character_with_known_feature()
        response = self.api_get(f"/api/v1/characters/{character_id}/combat-profile")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([feature["id"] for feature in response.json["features"]],
                         ["path.chevalier.rempart.rank-1.passive"])
        self.assertNotIn("class_id", response.json["character"])
        self.assertNotIn("species_id", response.json["character"])
        self.assertNotIn("character_options", response.json)
        feature = response.json["features"][0]
        self.assertNotIn("owner", feature)
        self.assertNotIn("rank_id", feature)
        self.assertNotIn("missing", feature["resolution"])
        self.assertNotIn("unstructured_rule", feature["resolution"])

    def test_combat_profile_is_smaller_than_the_complete_ruleset(self):
        character_id = self.character_with_known_feature()
        profile = self.api_get(f"/api/v1/characters/{character_id}/combat-profile")
        ruleset = self.api_get("/api/v1/rulesets/current")
        self.assertLess(len(profile.data), len(ruleset.data) / 10)
        cached = self.client.get(
            f"/api/v1/characters/{character_id}/combat-profile",
            headers=self.api_headers() | {"If-None-Match": profile.headers["ETag"]})
        self.assertEqual(cached.status_code, 304)

    def test_character_api_lists_available_snapshots(self):
        character_id = self.create_public_character()
        response = self.api_get("/api/v1/characters")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["characters"], [{
            "character_id": character_id, "version": 1, "name": "Aldren",
            "character_type": "player"}])

    def test_character_api_exposes_equipped_weapon_profile(self):
        character_id = self.create_public_character()
        self.insert_equipped_weapon(character_id)
        equipment = self.api_get(f"/api/v1/characters/{character_id}").json["equipment"]
        self.assertEqual(equipment[0]["damage"], {"count": 1, "sides": 8})
        self.assertEqual(equipment[0]["damage_type"], "physical")
        self.assertEqual(equipment[0]["slot"], "right_hand")

    def test_character_api_synchronizes_health_with_a_version(self):
        character_id = self.create_public_character()
        snapshot = self.api_get(f"/api/v1/characters/{character_id}").json
        payload = {"current_hp": 3, "expected_version": snapshot["version"]}
        response = self.api_put(f"/api/v1/characters/{character_id}/health", payload)
        stale = self.api_put(f"/api/v1/characters/{character_id}/health", payload)
        self.assertEqual((response.status_code, response.json["current_hp"]), (200, 3))
        self.assertEqual(stale.status_code, 409)

    def test_character_api_synchronizes_a_feature_resource(self):
        character_id, resource_key = self.character_with_api_resource()
        snapshot = self.api_get(f"/api/v1/characters/{character_id}").json
        path = f"/api/v1/characters/{character_id}/resources/{resource_key}"
        response = self.api_put(path, {"spent": 2, "expected_version": snapshot["version"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["resource"]["spent"], 2)
        refreshed = self.api_get(f"/api/v1/characters/{character_id}").json
        self.assertEqual((refreshed["version"], refreshed["resources"][0]["spent"]), (2, 2))

    def test_character_api_rejects_invalid_or_stale_resource_updates(self):
        character_id, resource_key = self.character_with_api_resource()
        path = f"/api/v1/characters/{character_id}/resources/{resource_key}"
        invalid = self.api_put(path, {"spent": 4, "expected_version": 1})
        valid = self.api_put(path, {"spent": 1, "expected_version": 1})
        stale = self.api_put(path, {"spent": 2, "expected_version": 1})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(stale.status_code, 409)

    def test_ruleset_api_exposes_a_cacheable_engine_bundle(self):
        response = self.api_get("/api/v1/rulesets/current")
        cached = self.client.get("/api/v1/rulesets/current",
                                 headers=self.api_headers() | {"If-None-Match":
                                                              response.headers["ETag"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["features"]), 194)
        self.assertTrue(response.headers["ETag"])
        self.assertEqual(cached.status_code, 304)

    def api_get(self, path):
        return self.client.get(path, headers=self.api_headers())

    def api_put(self, path, payload):
        return self.client.put(path, json=payload, headers=self.api_headers())

    def api_headers(self):
        return {"Authorization": "Bearer combat-bridge-token"}

    def insert_equipped_weapon(self, character_id):
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            database = get_db()
            database.execute(
                "INSERT INTO equipment (character_id, name, item_type, equipped, slot, "
                "damage_dice, damage_type) VALUES (?, 'Épée', 'weapon', 1, "
                "'right_hand', '1d8', 'physical')", (character_id,))
            database.commit()

    def character_with_api_resource(self):
        character_id = self.create_public_character()
        resource_key = "path.test.rank-1.active.uses"
        with self.app.app_context():
            path_id = self.insert_api_resource_path(character_id, resource_key)
            self.unlock_api_resource(character_id, path_id)
        return character_id, resource_key

    def character_with_known_feature(self):
        character_id = self.create_public_character()
        with self.app.app_context():
            path_id = self.insert_known_feature_path(character_id)
            self.unlock_api_resource(character_id, path_id)
        return character_id

    def insert_known_feature_path(self, character_id):
        from dnd_manager.infrastructure.database import get_db
        database = get_db()
        class_id = database.execute(
            "SELECT class_id FROM character WHERE id = ?", (character_id,)).fetchone()[0]
        ranks = [{"id": "path.chevalier.rempart.rank-1", "rank": 1,
                  "name": "Garde solidaire", "active": None,
                  "passive": {"effect": "Défense."}}]
        ranks.extend({"id": f"path.test.rank-{rank}", "rank": rank, "name": f"Rang {rank}",
                      "active": None, "passive": None} for rank in range(2, 6))
        cursor = database.execute(
            "INSERT INTO class_path (class_id, name, ranks_json, configured) "
            "VALUES (?, 'Voie connue', ?, 1)", (class_id, json.dumps(ranks)))
        return cursor.lastrowid

    def insert_api_resource_path(self, character_id, resource_key):
        from dnd_manager.infrastructure.database import get_db
        database = get_db()
        character = database.execute(
            "SELECT class_id FROM character WHERE id = ?", (character_id,)).fetchone()
        ranks = [{"id": "path.test.rank-1", "rank": 1, "name": "Épreuve",
                  "active": {"resource": {"id": resource_key, "maximum": 3}},
                  "passive": None}]
        ranks.extend({"id": f"path.test.rank-{rank}", "rank": rank, "name": f"Rang {rank}",
                      "active": None, "passive": None} for rank in range(2, 6))
        cursor = database.execute(
            "INSERT INTO class_path (class_id, name, ranks_json, configured) "
            "VALUES (?, 'Voie API', ?, 1)", (character["class_id"], json.dumps(ranks)))
        return cursor.lastrowid

    def unlock_api_resource(self, character_id, path_id):
        from dnd_manager.infrastructure.database import get_db
        database = get_db()
        database.execute(
            "INSERT INTO character_rank (character_id, path_type, path_id, rank) "
            "VALUES (?, 'class', ?, 1)", (character_id, path_id))
        database.commit()

    def test_public_paths_catalog_shows_two_paths_per_class_and_race(self):
        response = self.client.get("/voies")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Voies de chaque classe", page)
        self.assertIn("Rempart", page)
        self.assertIn("Berserker", page)
        self.assertIn("Voies de chaque race", page)
        self.assertIn("Dieu solaire", page)
        self.assertIn("Dieu occulte", page)
        self.assertEqual(page.count("Voie de classe</p>"), 14)
        self.assertEqual(page.count("Voie raciale</p>"), 24)
        self.assertNotIn("Murkmans", page)
        self.assertIn("<strong>Fureur écarlate</strong>", page)
        self.assertNotIn("<strong>Rang 1</strong>", page)
        self.assertIn("Les Chevaliers sont des combattants formés", page)
        self.assertIn("Les Dieux descendent des puissances", page)
        self.assertIn('<ul class="path-effect-list">', page)
        self.assertIn("Le personnage réduit toutes ses Défenses de 2", page)
        self.assertIn('<li>Attaque tous les ennemis adjacents', page)

    def test_path_creator_requires_gm_access(self):
        response = self.client.get("/mj/voies/nouvelle")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mj/connexion", response.headers["Location"])

    def test_gm_can_create_and_edit_a_class_path(self):
        self.login()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            class_id = get_db().execute(
                "SELECT id FROM character_class WHERE configured = 1 LIMIT 1"
            ).fetchone()["id"]
        response = self.client.post("/mj/voies/nouvelle",
                                    data=self.path_form(owner_id=class_id))
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            path = get_db().execute(
                "SELECT * FROM class_path WHERE name = 'Voie des braises'"
            ).fetchone()
            ranks = json.loads(path["ranks_json"])
            self.assertEqual((path["class_id"], path["configured"]), (class_id, 1))
            self.assertIsNone(path["stable_key"])
            self.assertEqual(len(ranks), 5)
            self.assertEqual(ranks[0]["name"], "Braise 1")
            self.assertEqual(ranks[0]["capabilities"], [])
        edited_values = self.path_form(owner_id=class_id, name="Voie des flammes")
        edited_values.update(rank_1_unlock_level="3",
                             rank_1_unlock_note="Valeur obsolète à ignorer")
        response = self.client.post(
            f"/mj/voies/class/{path['id']}/modifier",
            data=edited_values,
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn("Voie enregistrée.", page)
        self.assertNotIn("Ancien éditeur", page)
        self.assertNotIn("capability_json", page)
        self.assertEqual(page.count("Ajouter une capacité"), 5)
        catalogue = self.client.get("/voies").get_data(as_text=True)
        self.assertIn("Niveau minimal : 3", catalogue)
        self.assertNotIn("Valeur obsolète à ignorer", catalogue)
        self.assertNotIn("rank_1_unlock_note", page)

    def test_removed_legacy_capability_payload_is_ignored(self):
        self.login()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            class_id = get_db().execute(
                "SELECT id FROM character_class WHERE configured = 1 LIMIT 1"
            ).fetchone()["id"]
        values = self.path_form(owner_id=class_id, name="Voie automatique")
        values["rank_1_capability_json"] = json.dumps({
            "id": "path.temp.voie.rank-1.active", "support": "full",
            "targeting": {"selector": "single", "allegiance": ["enemy"]},
            "operations": [{
                "type": "damage", "target": "selected", "damage_type": "fire",
                "value": {"dice": [{"count": 2, "sides": 6}], "terms": [],
                          "constant": 0},
            }],
        })
        response = self.client.post("/mj/voies/nouvelle", data=values)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            database = get_db()
            row = database.execute(
                "SELECT id, ranks_json FROM class_path WHERE name = 'Voie automatique'"
            ).fetchone()
            self.assertEqual(json.loads(row["ranks_json"])[0]["capabilities"], [])
            count = database.execute(
                "SELECT COUNT(*) FROM path_capability pc JOIN path_rank pr "
                "ON pr.id=pc.path_rank_id JOIN path_definition pd "
                "ON pd.id=pr.path_definition_id WHERE pd.legacy_path_id=? "
                "AND pd.origin_type='class'",
                (row["id"],),
            ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_rank_can_receive_a_second_normalized_capability(self):
        self.login()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            path = get_db().execute(
                "SELECT id FROM class_path WHERE name = 'Rempart'"
            ).fetchone()
        url = f"/mj/voies/class/{path['id']}/rangs/1/capacites/nouvelle"
        values = {
            "csrf_token": self.csrf_token(), "name": "Riposte du gardien",
            "execution_mode": "triggered", "action_cost": "reaction",
            "structure_level": "structured", "trigger_event": "ally.targeted",
            "activation_limit": "once_per_turn",
            "operation_count": "2", "operation_0_type": "damage",
            "operation_0_target_ref": "target.primary", "operation_0_dice_count": "1",
            "operation_0_dice_sides": "8", "operation_0_damage_type": "physical",
            "operation_1_type": "manual_effect", "operation_1_target_ref": "source",
            "operation_1_description": "Échange sa position avec un allié.",
        }
        response = self.client.post(url, data=values, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Un allié est ciblé", page)
        self.assertIn("Une fois par tour", page)
        self.assertIn("Défense physique", page)
        self.assertIn("Qui reçoit cet effet ?", page)
        self.assertIn("Échange sa position avec un allié.", page)
        self.assertIn('<option value="manual_effect" selected>', page)
        edit_url = response.request.path
        # Les anciennes valeurs envoyées par un navigateur ne peuvent plus
        # désactiver la description automatique.
        values.update(structure_level="hybrid", manual_description="Texte obsolète.")
        response = self.client.post(edit_url, data=values, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertNotIn("Création de la description", page)
        self.assertNotIn("Précisions que les effets ne peuvent pas expliquer", page)
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            database = get_db()
            count = database.execute(
                "SELECT COUNT(*) FROM path_capability pc JOIN path_rank pr "
                "ON pr.id=pc.path_rank_id JOIN path_definition pd "
                "ON pd.id=pr.path_definition_id WHERE pd.legacy_path_id=? "
                "AND pd.origin_type='class' AND pr.rank=1", (path["id"],),
            ).fetchone()[0]
            self.assertEqual(count, 2)
            target = database.execute(
                "SELECT ct.selection_mode, ct.minimum_targets, ct.maximum_targets "
                "FROM capability_target ct JOIN path_capability pc "
                "ON pc.id=ct.capability_id WHERE pc.name=?",
                ("Riposte du gardien",),
            ).fetchone()
            self.assertEqual(dict(target), {
                "selection_mode": "manual",
                "minimum_targets": 1,
                "maximum_targets": 1,
            })
            columns = {row["name"] for row in database.execute(
                "PRAGMA table_info(path_capability)"
            ).fetchall()}
            self.assertNotIn("manual_description", columns)
            self.assertNotIn("structure_level", columns)
            obsolete = database.execute(
                "SELECT 1 FROM effect_node en JOIN path_capability pc "
                "ON pc.id=en.capability_id WHERE pc.name=? AND en.label=?",
                ("Riposte du gardien", "Texte obsolète."),
            ).fetchone()
            self.assertIsNone(obsolete)

    def test_permanent_capability_does_not_require_a_hidden_action_cost(self):
        self.login()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            path = get_db().execute(
                "SELECT id FROM class_path WHERE name = 'Rempart'"
            ).fetchone()
        response = self.client.post(
            f"/mj/voies/class/{path['id']}/rangs/1/capacites/nouvelle",
            data={
                "csrf_token": self.csrf_token(), "name": "Main experte permanente",
                "execution_mode": "permanent", "activation_limit": "",
                "operation_count": "1", "operation_0_type": "manual_effect",
                "operation_0_target_ref": "source",
                "operation_0_description": "Tests réalisés avec des outils : +4 au dé.",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Valeur invalide pour action_cost", response.get_data(as_text=True))
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            capability = get_db().execute(
                "SELECT action_cost FROM path_capability WHERE name='Main experte permanente'"
            ).fetchone()
            self.assertEqual(capability["action_cost"], "none")

    def test_racial_path_creator_computes_ability_bonuses(self):
        self.login()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            species_id = get_db().execute(
                "SELECT id FROM species WHERE configured = 1 LIMIT 1"
            ).fetchone()["id"]
        response = self.client.post(
            "/mj/voies/nouvelle",
            data=self.path_form("racial", species_id, "Voie des astres"),
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            path = get_db().execute(
                "SELECT strength_bonus, wisdom_bonus FROM racial_path "
                "WHERE name = 'Voie des astres'"
            ).fetchone()
            self.assertEqual((path["strength_bonus"], path["wisdom_bonus"]), (1, 1))

    def test_gm_dashboard_requires_login(self):
        response = self.client.get("/mj")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mj/connexion", response.headers["Location"])

    def test_gm_can_delete_a_character_and_its_related_data(self):
        character_id = self.create_public_character()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            database = get_db()
            database.execute(
                "INSERT INTO equipment (character_id, item_type, name) "
                "VALUES (?, 'tool', 'Objet à supprimer')", (character_id,),
            )
            database.commit()
        self.login()
        response = self.client.post(
            f"/mj/personnages/{character_id}/supprimer",
            data={"csrf_token": self.csrf_token()}, follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("a été supprimé définitivement", response.get_data(as_text=True))
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            database = get_db()
            self.assertIsNone(database.execute(
                "SELECT 1 FROM character WHERE id = ?", (character_id,)
            ).fetchone())
            self.assertIsNone(database.execute(
                "SELECT 1 FROM equipment WHERE character_id = ?", (character_id,)
            ).fetchone())

    def test_public_cannot_delete_a_character(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/mj/personnages/{character_id}/supprimer",
            data={"csrf_token": self.csrf_token()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mj/connexion", response.headers["Location"])

    def test_removed_player_and_journal_sections_do_not_exist(self):
        self.login()
        for path in ("/mj/joueurs", "/mj/journal"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_gm_can_login(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Vue MJ", response.get_data(as_text=True))

    def test_catalogue_administration_routes_do_not_exist(self):
        self.login()
        for path in (
            "/mj/classes",
            "/mj/classes/nouvelle",
            "/mj/classes/1/modifier",
            "/mj/especes",
            "/mj/especes/nouvelle",
            "/mj/especes/1/modifier",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_public_visitor_can_create_visible_player_character(self):
        class_id, species_id = self.create_catalogues()
        response = self.client.post(
            "/personnages/nouveau",
            data=self.character_form(
                class_id,
                species_id,
                character_type="enemy",
                visibility="gm",
                level="20",
            ),
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Aldren", page)
        self.assertIn("<dt>Classe</dt><dd>Gardien</dd>", page)
        self.assertIn("<dt>Niveau</dt><dd>1</dd>", page)
        self.assertIn(">Level up</button>", page)
        self.assertIn("Monter Aldren au niveau 2 ?", page)

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character = get_db().execute(
                """
                SELECT character_type, visibility, level, max_hp
                FROM character WHERE name = 'Aldren'
                """
            ).fetchone()
            self.assertEqual(character["character_type"], "player")
            self.assertEqual(character["visibility"], "campaign")
            self.assertEqual(character["level"], 1)
            self.assertEqual(character["max_hp"], 12)

    def test_public_creation_requires_exactly_27_points(self):
        class_id, species_id = self.create_catalogues()
        response = self.client.post(
            "/personnages/nouveau",
            data=self.character_form(class_id, species_id, strength="14"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("exactement 27 points", response.get_data(as_text=True))

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            count = get_db().execute("SELECT COUNT(*) FROM character").fetchone()[0]
            self.assertEqual(count, 0)

    def test_gm_can_create_secret_enemy_hidden_from_public(self):
        class_id, species_id = self.create_catalogues()
        self.login()
        response = self.client.post(
            "/personnages/nouveau",
            data=self.character_form(
                class_id,
                species_id,
                name="Dragon secret",
                owner_name="",
                character_type="enemy",
                visibility="gm",
                level="5",
            ),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dragon secret", response.get_data(as_text=True))

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character_id = get_db().execute(
                "SELECT id FROM character WHERE name = 'Dragon secret'"
            ).fetchone()["id"]

        with self.client.session_transaction() as session:
            session.clear()

        detail = self.client.get(f"/personnages/{character_id}")
        campaign = self.client.get("/")
        self.assertEqual(detail.status_code, 404)
        self.assertNotIn("Dragon secret", campaign.get_data(as_text=True))

    def test_public_visitor_can_change_hp_without_log(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/pv",
            data={
                "csrf_token": self.csrf_token(),
                "action": "damage",
                "amount": "5",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        # 5 dégâts physiques réduits par la Défense physique (+2 de Constitution).
        self.assertIn("12 → 9", response.get_data(as_text=True))

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            hp = database.execute(
                "SELECT current_hp FROM character WHERE id = ?", (character_id,)
            ).fetchone()["current_hp"]
            self.assertEqual(hp, 9)
            tables = {
                row[0]
                for row in database.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            self.assertNotIn("change_log", tables)

    def test_hp_can_be_saved_asynchronously(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/pv",
            data={
                "csrf_token": self.csrf_token(),
                "action": "set",
                "amount": "6",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["current_hp"], 6)
        self.assertTrue(response.json["ok"])

    def apply_damage(self, character_id, amount, **overrides):
        values = {"csrf_token": self.csrf_token(), "action": "damage", "amount": str(amount)}
        values.update(overrides)
        return self.client.post(f"/personnages/{character_id}/pv", data=values,
                                headers={"X-Requested-With": "XMLHttpRequest"})

    def restore_health(self, character_id):
        self.client.post(f"/personnages/{character_id}/pv",
                         data={"csrf_token": self.csrf_token(), "action": "rest"})

    def test_damage_uses_the_defense_matching_the_damage_type(self):
        # Constitution 15 donne +2 en Défense physique, Intelligence 10 donne +0 en élémentaire.
        character_id = self.create_public_character()
        physical = self.apply_damage(character_id, 5, damage_type="physical")
        self.restore_health(character_id)
        elemental = self.apply_damage(character_id, 5, damage_type="elemental")
        self.assertEqual(physical.json["current_hp"], 9)
        self.assertEqual(elemental.json["current_hp"], 7)

    def test_damage_ignores_a_defense_supplied_by_the_client(self):
        character_id = self.create_public_character()
        response = self.apply_damage(character_id, 5, damage_type="physical",
                                     physical_defense="99", elemental_defense="99",
                                     spiritual_defense="99")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["current_hp"], 9)

    def test_damage_rejects_an_unknown_damage_type(self):
        response = self.apply_damage(self.create_public_character(), 5,
                                     damage_type="radiant")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Type de dégâts invalide", response.json["message"])

    def test_damage_applies_defense_granted_by_equipped_armour(self):
        character_id = self.create_public_character()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            database.execute(
                "INSERT INTO equipment (character_id, name, item_type, equipped, slot, "
                "physical_bonus) VALUES (?, 'Cuirasse', 'armor', 1, 'armor', 3)",
                (character_id,),
            )
            database.commit()
        # 5 dégâts - (2 de Constitution + 3 de la cuirasse) = 0
        response = self.apply_damage(character_id, 5, damage_type="physical")
        self.assertEqual(response.json["current_hp"], 12)

    def test_estus_is_single_use_and_rest_restores_it(self):
        character_id = self.create_public_character()
        token = self.csrf_token()
        self.client.post(
            f"/personnages/{character_id}/pv",
            data={"csrf_token": token, "action": "damage", "amount": "5"},
        )
        estus = self.client.post(
            f"/personnages/{character_id}/pv",
            data={"csrf_token": token, "action": "estus"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(estus.status_code, 200)
        self.assertEqual(estus.json["current_hp"], estus.json["max_hp"])
        self.assertEqual(estus.json["estus_available"], 0)

        unavailable = self.client.post(
            f"/personnages/{character_id}/pv",
            data={"csrf_token": token, "action": "estus"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(unavailable.status_code, 400)

        rest = self.client.post(
            f"/personnages/{character_id}/pv",
            data={"csrf_token": token, "action": "rest"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(rest.status_code, 200)
        self.assertEqual(rest.json["estus_available"], 1)

    def test_limited_path_action_spends_a_charge_until_rest(self):
        character_id = self.create_public_character()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            character = database.execute(
                "SELECT class_id FROM character WHERE id = ?", (character_id,)
            ).fetchone()
            ranks = [
                {
                    "rank": 1,
                    "name": "Épreuve",
                    "active": {
                        "timing": "Action",
                        "uses": "2 fois par Repos au Feu",
                        "effect": "Effet de test.",
                    },
                    "passive": None,
                }
            ]
            ranks.extend(
                {
                    "rank": rank,
                    "name": f"Rang {rank}",
                    "active": None,
                    "passive": None,
                }
                for rank in range(2, 6)
            )
            path_id = database.execute(
                """
                INSERT INTO class_path
                    (class_id, name, ranks_json, configured)
                VALUES (?, 'Voie de test', ?, 1)
                """,
                (character["class_id"], json.dumps(ranks)),
            ).lastrowid
            database.execute(
                """
                INSERT INTO character_rank
                    (character_id, path_type, path_id, rank)
                VALUES (?, 'class', ?, 1)
                """,
                (character_id, path_id),
            )
            database.commit()

        token = self.csrf_token()
        page = self.client.get(f"/personnages/{character_id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("2/2 restantes", page.get_data(as_text=True))
        action_data = {
            "csrf_token": token,
            "path_type": "class",
            "path_id": str(path_id),
            "rank": "1",
        }
        first = self.client.post(
            f"/personnages/{character_id}/competences/utiliser",
            data=action_data,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        second = self.client.post(
            f"/personnages/{character_id}/competences/utiliser",
            data=action_data,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        exhausted = self.client.post(
            f"/personnages/{character_id}/competences/utiliser",
            data=action_data,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(first.json["remaining"], 1)
        self.assertEqual(second.json["remaining"], 0)
        self.assertEqual(exhausted.status_code, 400)

        self.client.post(
            f"/personnages/{character_id}/pv",
            data={"csrf_token": token, "action": "rest"},
        )
        restored = self.client.post(
            f"/personnages/{character_id}/competences/utiliser",
            data=action_data,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(restored.json["remaining"], 1)

    def test_public_character_accepts_a_local_portrait(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/portrait",
            data={
                "csrf_token": self.csrf_token(),
                "portrait": (
                    io.BytesIO(b"\x89PNG\r\n\x1a\nportrait"),
                    "portrait.png",
                ),
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        image = self.client.get(response.json["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.data, b"\x89PNG\r\n\x1a\nportrait")
        image.close()

    def test_hp_is_clamped_between_zero_and_maximum(self):
        character_id = self.create_public_character()
        self.client.post(
            f"/personnages/{character_id}/pv",
            data={
                "csrf_token": self.csrf_token(),
                "action": "damage",
                "amount": "99",
            },
        )
        self.client.post(
            f"/personnages/{character_id}/pv",
            data={
                "csrf_token": self.csrf_token(),
                "action": "heal",
                "amount": "99",
            },
        )
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            hp = get_db().execute(
                "SELECT current_hp FROM character WHERE id = ?", (character_id,)
            ).fetchone()["current_hp"]
            self.assertEqual(hp, 12)

    def test_removed_character_text_section_is_not_exposed(self):
        character_id = self.create_public_character()
        response = self.client.get(f"/personnages/{character_id}")
        page = response.get_data(as_text=True)
        removed_endpoint = self.client.post(
            f"/personnages/{character_id}/textes",
            data={"csrf_token": self.csrf_token()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<h2>Description</h2>", page)
        self.assertNotIn("<h2>Informations personnelles</h2>", page)
        self.assertEqual(removed_endpoint.status_code, 404)

    def test_equipped_item_updates_displayed_defenses(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/equipement/nouveau",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Armure runique",
                "item_type": "armor",
                "quantity": "1",
                "equipped": "1",
                "physical_bonus": "2",
                "elemental_bonus": "1",
                "spiritual_bonus": "-1",
                "notes": "Une vieille armure",
            },
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        # CON 15 donne +2, auquel l'armure ajoute +2.
        self.assertIn("<strong>+4</strong>", page)
        inventory = self.client.get(
            f"/personnages/{character_id}/equipement"
        ).get_data(as_text=True)
        self.assertIn("Armure runique", inventory)
        self.assertIn("+2 physique", inventory)

    def test_consumable_use_is_atomic_and_removes_last_item(self):
        character_id = self.create_public_character()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            equipment_id = database.execute(
                "INSERT INTO equipment (character_id, name, item_type, quantity) "
                "VALUES (?, 'Fiole', 'consumable', 1)",
                (character_id,),
            ).lastrowid
            database.commit()
        response = self.client.post(
            f"/personnages/{character_id}/equipement/{equipment_id}/utiliser",
            data={"csrf_token": self.csrf_token()},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            item = get_db().execute(
                "SELECT 1 FROM equipment WHERE id = ?", (equipment_id,)
            ).fetchone()
        self.assertIsNone(item)

    def test_equipped_accessory_updates_ability_and_derived_values(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/equipement/nouveau",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Anneau du sage",
                "item_type": "accessory",
                "quantity": "1",
                "equipped": "1",
                "physical_bonus": "0",
                "elemental_bonus": "0",
                "spiritual_bonus": "0",
                "stat": "INT",
                "stat_bonus": "2",
            },
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("10 + 2 accessoires", page)
        # Une Intelligence effective de 12 donne +1 en Défense élémentaire.
        self.assertIn("<strong>+1</strong>", page)

    def test_constitution_accessory_recalculates_maximum_hp(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/equipement/nouveau",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Anneau de vigueur",
                "item_type": "accessory",
                "quantity": "1",
                "equipped": "1",
                "physical_bonus": "0",
                "elemental_bonus": "0",
                "spiritual_bonus": "0",
                "stat": "CON",
                "stat_bonus": "2",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character = get_db().execute(
                "SELECT current_hp, max_hp FROM character WHERE id = ?",
                (character_id,),
            ).fetchone()
            self.assertEqual(character["max_hp"], 13)
            self.assertEqual(character["current_hp"], 13)

    def test_hand_equipment_uses_right_then_left_slot(self):
        character_id = self.create_public_character()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            item_ids = []
            for name, item_type in (
                ("Épée", "weapon"),
                ("Bouclier", "shield"),
                ("Catalyseur", "tool"),
            ):
                item_ids.append(
                    database.execute(
                        """
                        INSERT INTO equipment (character_id, name, item_type)
                        VALUES (?, ?, ?)
                        """,
                        (character_id, name, item_type),
                    ).lastrowid
                )
            database.commit()

        token = self.csrf_token()
        for item_id in item_ids[:2]:
            response = self.client.post(
                f"/personnages/{character_id}/equipement/{item_id}/equiper",
                data={"csrf_token": token},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            self.assertEqual(response.status_code, 200)
        full = self.client.post(
            f"/personnages/{character_id}/equipement/{item_ids[2]}/equiper",
            data={"csrf_token": token},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(full.status_code, 400)

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            slots = {
                row["name"]: row["slot"]
                for row in get_db().execute(
                    """
                    SELECT name, slot FROM equipment
                    WHERE id IN (?, ?, ?)
                    """,
                    item_ids,
                ).fetchall()
            }
            self.assertEqual(slots["Épée"], "right_hand")
            self.assertEqual(slots["Bouclier"], "left_hand")
            self.assertEqual(slots["Catalyseur"], "")

    def test_quick_item_creation_opens_an_editable_detail(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/equipement/rapide",
            data={"csrf_token": self.csrf_token(), "item_type": "weapon"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["refresh_sheet"])
        equipment_id = response.json["selected_item_id"]

        page = self.client.get(f"/personnages/{character_id}").get_data(as_text=True)
        self.assertIn(f'data-inventory-detail="{equipment_id}"', page)
        self.assertIn('class="inventory-detail-name"', page)
        self.assertIn("Nouvelle arme", page)

    def test_item_icon_library_is_filtered_and_paginated(self):
        response = self.client.get("/personnages/bibliotheque-icones/spell")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertLessEqual(len(response.json["icons"]), 200)
        self.assertTrue(response.json["icons"])
        self.assertTrue(
            all(icon["path"].startswith("04_spells/") for icon in response.json["icons"])
        )
        icon_response = self.client.get(response.json["icons"][0]["url"])
        self.assertEqual(icon_response.status_code, 200)
        icon_response.close()

    def test_tool_icon_library_includes_catalysts(self):
        response = self.client.get("/personnages/bibliotheque-icones/tool")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["icons"])
        self.assertTrue(
            all(
                icon["path"].startswith("07_catalysts/")
                for icon in response.json["icons"]
            )
        )

    def test_player_can_choose_and_save_an_item_icon(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/equipement/rapide",
            data={"csrf_token": self.csrf_token(), "item_type": "spell"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        equipment_id = response.json["selected_item_id"]
        icon_path = "04_spells/MENU_Knowledge_04100.PNG"

        response = self.client.post(
            f"/personnages/{character_id}/equipement/{equipment_id}/modifier",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Flèche d’âme",
                "item_type": "spell",
                "quantity": "1",
                "equipped": "0",
                "physical_bonus": "0",
                "elemental_bonus": "0",
                "spiritual_bonus": "0",
                "damage_dice": "2d6",
                "damage_type": "elemental",
                "uses": "3 fois par repos",
                "stat": "",
                "stat_bonus": "0",
                "icon_path": icon_path,
                "effect": "Inflige des dégâts élémentaires.",
                "notes": "",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            saved_icon = get_db().execute(
                "SELECT icon_path FROM equipment WHERE id = ?", (equipment_id,)
            ).fetchone()["icon_path"]
        self.assertEqual(saved_icon, icon_path)
        page = self.client.get(f"/personnages/{character_id}").get_data(as_text=True)
        self.assertIn("data-icon-picker-toggle", page)
        self.assertNotIn("Choisir une icône", page)
        self.assertIn("MENU_Knowledge_04100.PNG", page)
        self.assertNotIn(">Notes<", page)

    def test_item_icon_route_rejects_paths_outside_library(self):
        response = self.client.get(
            "/personnages/icones/fichier/../../schema.sql"
        )
        self.assertEqual(response.status_code, 404)

    def test_inventory_interface_assets_are_served_safely(self):
        for path in (
            "menu-dish.png",
            "sprite-1-1.png",
            "right_hand.png",
            "left_hand.png",
            "armor.png",
            "ring.png",
            "stamp.png",
        ):
            response = self.client.get(f"/personnages/interface/{path}")
            self.assertEqual(response.status_code, 200)
            response.close()

        self.assertEqual(
            self.client.get("/personnages/interface/../schema.sql").status_code,
            404,
        )

    def test_public_cannot_modify_secret_character(self):
        class_id, species_id = self.create_catalogues()
        self.login()
        self.client.post(
            "/personnages/nouveau",
            data=self.character_form(
                class_id,
                species_id,
                name="Secret à protéger",
                owner_name="",
                character_type="enemy",
                visibility="gm",
            ),
        )
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character_id = get_db().execute(
                "SELECT id FROM character WHERE name = 'Secret à protéger'"
            ).fetchone()["id"]
        with self.client.session_transaction() as session:
            session.clear()

        response = self.client.post(
            f"/personnages/{character_id}/pv",
            data={
                "csrf_token": self.csrf_token(),
                "action": "damage",
                "amount": "5",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_character_administration_requires_gm(self):
        character_id = self.create_public_character()
        response = self.client.get(f"/mj/personnages/{character_id}/modifier")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mj/connexion", response.headers["Location"])

    def test_gm_level_up_recalculates_full_hp_to_new_maximum(self):
        character_id = self.create_public_character()
        self.login()
        response = self.client.post(
            f"/mj/personnages/{character_id}/modifier",
            data=self.admin_character_form(level="2"),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("20", response.get_data(as_text=True))

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character = get_db().execute(
                "SELECT level, current_hp, max_hp FROM character WHERE id = ?",
                (character_id,),
            ).fetchone()
            self.assertEqual(character["level"], 2)
            self.assertEqual(character["max_hp"], 20)
            self.assertEqual(character["current_hp"], 20)

    def test_gm_level_up_preserves_current_hp_when_character_is_wounded(self):
        character_id = self.create_public_character()
        self.client.post(
            f"/personnages/{character_id}/pv",
            data={
                "csrf_token": self.csrf_token(),
                "action": "damage",
                "amount": "5",
            },
        )
        self.login()
        self.client.post(
            f"/mj/personnages/{character_id}/modifier",
            data=self.admin_character_form(level="2"),
        )
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character = get_db().execute(
                "SELECT current_hp, max_hp FROM character WHERE id = ?",
                (character_id,),
            ).fetchone()
            # 12 - (5 - 2 de Défense physique) = 9, conservé après le passage au niveau 2.
            self.assertEqual(character["current_hp"], 9)
            self.assertEqual(character["max_hp"], 20)

    def test_gm_cannot_lower_level_or_break_point_buy(self):
        character_id = self.create_public_character()
        self.login()
        self.client.post(
            f"/mj/personnages/{character_id}/modifier",
            data=self.admin_character_form(level="2"),
        )
        response = self.client.post(
            f"/mj/personnages/{character_id}/modifier",
            data=self.admin_character_form(level="1", strength="14"),
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            "niveau ne peut pas diminuer" in page
            or "exactement 27 points" in page
        )

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            character = get_db().execute(
                "SELECT level, strength FROM character WHERE id = ?",
                (character_id,),
            ).fetchone()
            self.assertEqual(character["level"], 2)
            self.assertEqual(character["strength"], 15)

    def test_gm_can_hide_character(self):
        character_id = self.create_public_character()
        self.login()
        self.client.post(
            f"/mj/personnages/{character_id}/modifier",
            data=self.admin_character_form(visibility="gm"),
        )
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get(f"/personnages/{character_id}").status_code, 404)

    def test_gm_can_duplicate_character_with_equipment(self):
        character_id = self.create_public_character()
        self.client.post(
            f"/personnages/{character_id}/equipement/nouveau",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Bouclier",
                "item_type": "shield",
                "quantity": "1",
                "equipped": "1",
                "physical_bonus": "2",
                "elemental_bonus": "0",
                "spiritual_bonus": "0",
                "notes": "",
            },
        )
        self.login()
        response = self.client.post(
            f"/mj/personnages/{character_id}/dupliquer",
            data={"csrf_token": self.csrf_token()},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Aldren — copie", response.get_data(as_text=True))

        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            duplicate = database.execute(
                "SELECT id, owner_id FROM character WHERE name = 'Aldren — copie'"
            ).fetchone()
            self.assertIsNone(duplicate["owner_id"])
            equipment_count = database.execute(
                "SELECT COUNT(*) FROM equipment WHERE character_id = ?",
                (duplicate["id"],),
            ).fetchone()[0]
            self.assertEqual(equipment_count, 1)

    def test_public_cannot_duplicate_character(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/mj/personnages/{character_id}/dupliquer",
            data={"csrf_token": self.csrf_token()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mj/connexion", response.headers["Location"])

    def test_security_headers_are_added(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")

    def test_gm_login_is_rate_limited_after_five_failures(self):
        for _ in range(5):
            response = self.client.post(
                "/mj/connexion",
                data={
                    "password": "incorrect",
                    "csrf_token": self.csrf_token(),
                },
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/mj/connexion",
            data={"password": "dragon", "csrf_token": self.csrf_token()},
        )
        self.assertEqual(response.status_code, 429)

    def test_stale_gm_character_form_is_rejected(self):
        character_id = self.create_public_character()
        self.login()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            database.execute(
                "UPDATE character SET version = 2 WHERE id = ?", (character_id,)
            )
            database.commit()

        response = self.client.post(
            f"/mj/personnages/{character_id}/modifier",
            data=self.admin_character_form(version="1", level="2"),
        )
        self.assertEqual(response.status_code, 409)

    def test_gm_dashboard_filters_type_visibility_and_owner(self):
        visible_id = self.create_public_character(name="Héros visible")
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            source = database.execute(
                "SELECT * FROM character WHERE id = ?", (visible_id,)
            ).fetchone()
            database.execute(
                """
                INSERT INTO character
                    (
                        class_id, species_id, name, character_type, visibility,
                        level, strength, dexterity, constitution, intelligence,
                        wisdom, charisma, current_hp, max_hp
                    )
                VALUES (?, ?, 'Ennemi secret', 'enemy', 'gm', 1,
                        15, 10, 15, 10, 13, 8, 12, 12)
                """,
                (source["class_id"], source["species_id"]),
            )
            database.commit()

        self.login()
        response = self.client.get(
            "/mj?type=enemy&visibility=gm&owner=none"
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ennemi secret", page)
        self.assertNotIn("Héros visible", page)

    def test_character_sheet_displays_species_capabilities(self):
        character_id = self.create_public_character()
        response = self.client.get(f"/personnages/{character_id}")
        page = response.get_data(as_text=True)
        self.assertIn("Une espèce polyvalente.", page)
        self.assertIn("Débrouillardise, compétence supplémentaire, polyvalence.", page)
        self.assertIn("Moyenne", page)
        self.assertIn("30", page)

    def test_species_config_bonuses_are_added_to_defenses(self):
        class_id, _ = self.create_catalogues()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            racial_path = get_db().execute(
                """
                SELECT rp.id, rp.species_id
                FROM racial_path rp
                WHERE rp.name = 'Dieu solaire'
                """
            ).fetchone()
        response = self.client.post(
            "/personnages/nouveau",
            data=self.character_form(
                class_id,
                racial_path["species_id"],
                racial_path_id=str(racial_path["id"]),
            ),
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn("Défenses raciales", page)
        self.assertIn("defense-physical", page)
        self.assertIn("<strong>+4</strong>", page)
        self.assertIn("defense-elemental", page)

    def test_merged_origin_defenses_are_exposed_by_character_api(self):
        class_id, _ = self.create_catalogues()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            path = get_db().execute(
                "SELECT id, species_id FROM racial_path WHERE name = 'Enfant de la Mort'"
            ).fetchone()
        self.client.post("/personnages/nouveau", data=self.character_form(
            class_id, path["species_id"], racial_path_id=str(path["id"])))
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db
            database = get_db()
            character_id = database.execute(
                "SELECT id FROM character ORDER BY id DESC LIMIT 1"
            ).fetchone()["id"]
            database.execute("UPDATE character SET racial_path_id = ? WHERE id = ?",
                             (path["id"], character_id))
            database.commit()
        defenses = self.api_get(f"/api/v1/characters/{character_id}").json["base_defenses"]
        self.assertEqual({item["key"]: item["value"] for item in defenses},
                         {"physical": 1, "elemental": 0, "spiritual": 4})
        snapshot = self.api_get(f"/api/v1/characters/{character_id}").json
        self.assertEqual(snapshot["racial_path_id"],
                         "path.enfant-des-tenebres.enfant-de-la-mort")

    def test_character_selects_one_bonus_but_sees_all_available_paths(self):
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            class_path = database.execute(
                """
                SELECT cp.id AS path_id, cp.class_id
                FROM class_path cp
                WHERE cp.name = 'Rempart'
                """
            ).fetchone()
            racial_path = database.execute(
                """
                SELECT rp.id AS path_id, rp.species_id
                FROM racial_path rp
                WHERE rp.name = 'Dieu solaire'
                """
            ).fetchone()
        response = self.client.post(
            "/personnages/nouveau",
            data=self.character_form(
                class_path["class_id"],
                racial_path["species_id"],
                racial_path_id=str(racial_path["path_id"]),
            ),
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn("Rempart", page)
        self.assertIn("Berserker", page)
        self.assertIn("Dieu solaire", page)
        self.assertIn("Dieu occulte", page)
        self.assertIn("Débloque un rang 1 racial.", page)
        self.assertIn("Forteresse vivante", page)
        self.assertIn("Bonus racial actif", page)

        character_url = response.request.path
        response = self.client.post(
            f"{character_url}/bonus-racial",
            data={
                "csrf_token": self.csrf_token(),
                "racial_path_id": str(racial_path["path_id"]),
            },
            follow_redirects=True,
        )
        self.assertIn(
            "Débloque d’abord le rang 1 de cette voie.",
            response.get_data(as_text=True),
        )
        response = self.client.post(
            f"{character_url}/rangs",
            data={
                "csrf_token": self.csrf_token(),
                "path_type": "racial",
                "path_id": str(racial_path["path_id"]),
            },
            follow_redirects=True,
        )
        self.assertIn(
            "Dieu solaire · +2 CHA, +1 SAG",
            response.get_data(as_text=True),
        )
        response = self.client.post(
            f"{character_url}/bonus-racial",
            data={
                "csrf_token": self.csrf_token(),
                "racial_path_id": str(racial_path["path_id"]),
            },
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn("Bonus de Dieu solaire appliqué.", page)
        self.assertIn("8 + 2 voie raciale", page)

    def test_levels_grant_path_points_and_permanent_rank_bonuses(self):
        self.login()
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            class_path = database.execute(
                "SELECT id, class_id FROM class_path WHERE name = 'Rempart'"
            ).fetchone()
            racial_path = database.execute(
                "SELECT id, species_id FROM racial_path WHERE name = 'Dieu solaire'"
            ).fetchone()
            other_racial_path = database.execute(
                "SELECT id FROM racial_path WHERE name = 'Dieu occulte'"
            ).fetchone()
        response = self.client.post(
            "/personnages/nouveau",
            data=self.character_form(
                class_path["class_id"],
                racial_path["species_id"],
                class_path_id=str(class_path["id"]),
                racial_path_id=str(racial_path["id"]),
                level="3",
                character_type="player",
                visibility="campaign",
            ),
            follow_redirects=True,
        )
        character_url = response.request.path
        self.assertIn("points disponibles", response.get_data(as_text=True))

        for expected_points in (2, 1):
            response = self.client.post(
                f"{character_url}/rangs",
                data={
                    "csrf_token": self.csrf_token(),
                    "path_type": "racial",
                    "path_id": str(racial_path["id"]),
                },
                follow_redirects=True,
            )
            self.assertIn(
                f"<strong>{expected_points}</strong>",
                response.get_data(as_text=True),
            )

        page = response.get_data(as_text=True)
        self.assertIn("defense-elemental", page)
        self.assertIn("<strong>+4</strong>", page)
        response = self.client.post(
            f"{character_url}/rangs",
            data={
                "csrf_token": self.csrf_token(),
                "path_type": "racial",
                "path_id": str(other_racial_path["id"]),
            },
            follow_redirects=True,
        )
        self.assertIn("<strong>0</strong>", response.get_data(as_text=True))
        response = self.client.post(
            f"{character_url}/rangs",
            data={
                "csrf_token": self.csrf_token(),
                "path_type": "class",
                "path_id": str(class_path["id"]),
            },
            follow_redirects=True,
        )
        self.assertIn("Aucun point de voie disponible.", response.get_data(as_text=True))

    def test_public_player_can_level_up_from_character_sheet(self):
        character_id = self.create_public_character()
        response = self.client.post(
            f"/personnages/{character_id}/niveau",
            data={"csrf_token": self.csrf_token()},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "Niveau 2 atteint : 1 point de voie gagné.")
        page = self.client.get(f"/personnages/{character_id}").get_data(as_text=True)
        self.assertIn("<dt>Niveau</dt><dd>2</dd>", page)
        self.assertIn("<strong>2</strong>", page)

    def test_archive_routes_do_not_exist(self):
        character_id = self.create_public_character()
        self.login()
        paths = (
            "/mj/classes/1/statut",
            "/mj/especes/1/statut",
            f"/mj/personnages/{character_id}/statut",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.post(
                    path,
                    data={"csrf_token": self.csrf_token()},
                )
                self.assertEqual(response.status_code, 404)

    def test_health_endpoint_checks_database(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_database_outage_returns_controlled_service_unavailable(self):
        failure = sqlite3.OperationalError("storage offline")
        with self.silenced_logger(), patch("dnd_manager.campaign.http.get_db",
                                           side_effect=failure):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("storage offline", response.get_data(as_text=True))

    def test_database_outage_is_logged_as_an_incident(self):
        failure = sqlite3.OperationalError("storage offline")
        with self.assertLogs(self.app.logger, level="ERROR") as logs:
            with patch("dnd_manager.campaign.http.get_db", side_effect=failure):
                self.client.get("/health")
        self.assertIn("storage offline", "\n".join(logs.output))

    def test_public_list_stays_fast_with_realistic_volume(self):
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            database.executemany(
                """
                INSERT INTO character
                    (
                        name, character_type, visibility, current_hp, max_hp
                    )
                VALUES (?, 'npc', 'campaign', 10, 10)
                """,
                [(f"PNJ {index:03d}",) for index in range(500)],
            )
            database.commit()

        started = time.perf_counter()
        response = self.client.get("/")
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2.0)

    def test_secret_character_is_not_shown_publicly(self):
        with self.app.app_context():
            from dnd_manager.infrastructure.database import get_db

            database = get_db()
            database.execute(
                """
                INSERT INTO character
                    (name, character_type, visibility, current_hp, max_hp)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("Dragon secret", "enemy", "gm", 100, 100),
            )
            database.commit()

        response = self.client.get("/")
        self.assertNotIn("Dragon secret", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path

from scripts.build_engine_data import build


class EngineDataTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(Path("game_data.json").read_text(encoding="utf-8"))
        cls.bundle = json.loads(Path("engine_data.json").read_text(encoding="utf-8"))

    def test_generated_bundle_is_current(self):
        self.assertEqual(self.bundle, build(self.source))

    def test_every_rule_block_has_one_engine_feature(self):
        expected = sum(bool(rank.get(mode))
                       for group in ("classes", "races")
                       for option in self.source[group]
                       for path in option["paths"]
                       for rank in path["ranks"]
                       for mode in ("active", "passive"))
        self.assertEqual(len(self.bundle["features"]), expected)

    def test_full_features_have_structured_operations(self):
        full = [item for item in self.bundle["features"]
                if item["resolution"]["support"] == "full"]
        self.assertTrue(full)
        self.assertTrue(all(item["resolution"]["operations"] for item in full))

    def test_natural_weapon_is_fully_structured(self):
        feature = self.feature("path.hommes-champignons.fongique-ancestral.rank-1.passive")
        operation = feature["resolution"]["operations"][0]
        self.assertEqual(operation["type"], "attack_profile")
        self.assertEqual(operation["damage"]["dice"], {"count": 1, "sides": 10})
        self.assertEqual(operation["damage_type"], "physical")

    def test_temporary_defense_has_explicit_targets_and_duration(self):
        feature = self.feature("path.chevalier.rempart.rank-3.active")
        resolution = feature["resolution"]
        self.assertEqual(resolution["targeting"]["area"]["distance"]["value"], 3)
        self.assertEqual(len(resolution["operations"]), 3)
        self.assertTrue(all(operation["duration"] == {"value": 3, "unit": "turn"}
                            for operation in resolution["operations"]))

    def test_new_rules_increase_full_automation_coverage(self):
        self.assertEqual(self.bundle["coverage"]["full"], 64)
        self.assertEqual(self.bundle["coverage"]["partial"], 130)

    def test_temporary_bonus_damage_is_fully_structured(self):
        feature = self.feature("path.pyromancien.adepte-du-chaos.rank-2.active")
        operation = feature["resolution"]["operations"][0]
        self.assertEqual(operation["damage_type"], "fire")
        self.assertEqual(operation["frequency"], "once_per_turn")
        self.assertEqual(operation["duration"], {"value": 3, "unit": "turn"})

    def test_every_extracted_damage_type_exists_in_catalogue(self):
        known = set(self.bundle["definitions"]["damage_types"])
        extracted = {damage_type for feature in self.bundle["features"]
                     for damage_type in feature["resolution"].get(
                         "facts", {}).get("damage_types", ())}
        self.assertLessEqual(extracted, known)

    def test_regeneration_exposes_trigger_frequency_and_duration(self):
        feature = self.feature("path.dragons.dragon-cristallin.rank-3.passive")
        operation = feature["resolution"]["operations"][0]
        self.assertEqual(operation["type"], "regeneration")
        self.assertEqual(operation["trigger"]["type"], "health_below_fraction")
        self.assertEqual(operation["frequency"], "once_per_turn")
        self.assertEqual(operation["duration"]["value"], 3)

    def test_immunities_are_independent_typed_operations(self):
        feature = self.feature(
            "path.enfant-des-tenebres.enfant-de-la-mort.rank-1.passive")
        statuses = {operation["status"] for operation in feature[
            "resolution"]["operations"]}
        self.assertEqual(statuses, {"ordinary_disease", "ordinary_poison"})

    def test_direct_damage_distinguishes_cost_and_target(self):
        feature = self.feature("path.pyromancien.profane.rank-1.active")
        self_damage, target_damage = feature["resolution"]["operations"]
        self.assertEqual((self_damage["target"], self_damage["damage_type"]),
                         ("self", "untyped"))
        self.assertTrue(self_damage["bypass_defense"])
        self.assertEqual((target_damage["target"], target_damage["damage_type"]),
                         ("selected", "dark"))

    def test_extra_attack_has_an_explicit_duration(self):
        feature = self.feature(
            "path.enfant-des-tenebres.enfant-des-abysses.rank-4.active")
        operation = feature["resolution"]["operations"][0]
        self.assertEqual(operation, {
            "type": "extra_attack", "target": "selected", "count": 1,
            "duration": {"value": 3, "unit": "turn"}})

    def test_damage_reduction_keeps_dice_and_ability_term(self):
        feature = self.feature("path.chevalier.rempart.rank-2.active")
        operation = feature["resolution"]["operations"][0]
        self.assertEqual(operation["type"], "reduce_damage")
        self.assertEqual(operation["value"]["dice"], {"count": 1, "sides": 8})
        self.assertEqual(operation["value"]["terms"][0]["ability"], "constitution")

    def test_conditional_defense_bonus_names_triggering_damage_type(self):
        feature = self.feature("path.humains.porte-braise.rank-2.passive")
        operation = feature["resolution"]["operations"][0]
        self.assertEqual(operation["condition"], {"type": "damage_type", "value": "dark"})

    def test_choice_exposes_every_elemental_branch(self):
        feature = self.feature("path.specialiste.ingenieur.rank-3.active")
        choice = feature["resolution"]["operations"][0]
        self.assertEqual(choice["type"], "choice")
        self.assertEqual({option["id"] for option in choice["options"]},
                         {"fire", "lightning", "ice", "magic"})

    def test_persistent_area_exposes_runtime_triggers(self):
        feature = self.feature("path.pyromancien.adepte-du-chaos.rank-3.active")
        operation = feature["resolution"]["operations"][0]
        self.assertEqual(operation["triggers"], ["enter_area", "start_turn"])
        self.assertEqual(operation["duration"], {"value": 3, "unit": "turn"})

    def test_mixed_area_filters_allies_and_enemies(self):
        feature = self.feature(
            "path.hommes-champignons.mycelien-sporifere.rank-5.active")
        operations = feature["resolution"]["operations"]
        self.assertEqual([value["target_filter"] for value in operations],
                         ["ally", "enemy"])

    def test_choice_options_can_define_distinct_targeting(self):
        feature = self.feature("path.clerc.pretre.rank-1.active")
        options = feature["resolution"]["operations"][0]["options"]
        self.assertEqual(options[0]["targeting"]["allegiance"], ["ally"])
        self.assertEqual(options[1]["targeting"]["allegiance"], ["enemy"])

    def test_lethal_shot_ignores_half_physical_defense(self):
        feature = self.feature("path.roublard.archer.rank-5.active")
        lethal = feature["resolution"]["operations"][0]["options"][0]
        penetration = lethal["operations"][1]
        self.assertEqual((penetration["defense"], penetration["factor"]),
                         ("physical", 0.5))

    def test_full_feature_descriptions_are_generated(self):
        feature = next(item for item in self.bundle["features"]
                       if item["id"] == (
                           "path.enfant-des-tenebres."
                           "enfant-de-la-mort.rank-2.active"
                       ))
        self.assertEqual(feature["description"], "Vous récupérez 2d8 + MOD Constitution PV.")

    def test_passive_defense_description_is_generated(self):
        feature = next(item for item in self.bundle["features"]
                       if item["id"] == "path.geants.geant-beant.rank-2.passive")
        self.assertEqual(feature["description"],
                         "Vous gagnez +3 en Défense physique. "
                         "Vous subissez -2 en Défense élémentaire.")

    def test_feature_identifiers_are_unique(self):
        identifiers = [item["id"] for item in self.bundle["features"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_every_non_full_feature_has_extracted_facts(self):
        partial = [item for item in self.bundle["features"]
                   if item["resolution"]["support"] == "partial"]
        self.assertTrue(partial)
        self.assertTrue(all("facts" in item["resolution"] for item in partial))
        self.assertTrue(all(item["resolution"]["operations"] for item in partial))

    def test_partial_damage_has_a_typed_operation_skeleton(self):
        feature = next(item for item in self.bundle["features"]
                       if item["id"] == "path.sorcier.cryomancien.rank-4.active")
        operation_types = [item["type"] for item in feature["resolution"]["operations"]]
        self.assertIn("damage", operation_types)
        self.assertTrue(all(not item["complete"] for item in feature["resolution"]["operations"]))

    def test_coverage_accounts_for_every_feature(self):
        coverage = self.bundle["coverage"]
        self.assertEqual(coverage["total"],
                         coverage["full"] + coverage["partial"] + coverage["reference"])

    def test_no_feature_is_left_as_an_unclassified_reference(self):
        self.assertEqual(self.bundle["coverage"]["reference"], 0)

    def test_missing_save_difficulties_are_reported(self):
        self.assertGreater(self.bundle["coverage"]["missing"]["saving_throw_difficulty"], 0)

    def test_bonfire_rest_is_an_alias_of_long_rest(self):
        aliases = self.bundle["definitions"]["rest_aliases"]
        self.assertEqual(aliases["bonfire_rest"], "long_rest")

    def test_bonfire_wording_extracts_a_long_rest_trigger(self):
        feature = next(item for item in self.bundle["features"]
                       if item["id"] == "path.sorcier.cryomancien.rank-2.passive")
        self.assertEqual(feature["resolution"]["facts"]["rest_triggers"], ["long_rest"])

    def test_special_resources_have_stable_definitions(self):
        definitions = self.bundle["definitions"]["resources"]
        self.assertEqual(definitions["humanity"]["value_type"], "counter")
        self.assertEqual(definitions["curse"]["value_type"], "collection")

    def test_special_resource_usage_reports_missing_character_state(self):
        feature = next(item for item in self.bundle["features"]
                       if item["id"] == "path.humains.porte-signe.rank-4.active")
        self.assertIn("humanity", feature["resolution"]["facts"]["resource_refs"])
        self.assertIn("resource_state", feature["resolution"]["missing"])

    def test_missing_species_profiles_are_reported(self):
        gaps = self.bundle["coverage"]["catalog_gaps"]
        self.assertEqual(gaps, {"species_size": 12, "species_speed": 12})

    def test_merged_soulborn_race_has_two_engine_paths(self):
        owners = {item["owner"]["path_id"] for item in self.bundle["features"]
                  if item["owner"]["id"] == "species.enfant-des-tenebres"}
        self.assertEqual(owners, {
            "path.enfant-des-tenebres.enfant-de-la-mort",
            "path.enfant-des-tenebres.enfant-des-abysses",
        })

    def test_character_options_include_dark_child_origins(self):
        species = next(item for item in self.bundle["character_options"]["species"]
                       if item["id"] == "species.enfant-des-tenebres")
        self.assertEqual(species["name"], "Enfant des Ténèbres")
        self.assertEqual([path["name"] for path in species["paths"]],
                         ["Enfant de la Mort", "Enfant des Abysses"])

    def test_old_nito_and_manus_identifiers_have_aliases(self):
        aliases = self.bundle["definitions"]["identifier_aliases"]
        self.assertEqual(aliases["species.creations-de-nito"],
                         "species.enfant-des-tenebres")
        self.assertEqual(aliases["path.enfants-de-manus.bete-abyssale.rank-2.active"],
                         "path.enfant-des-tenebres.enfant-des-abysses.rank-2.active")

    def test_murkman_features_are_absent(self):
        identifiers = [item["id"] for item in self.bundle["features"]]
        self.assertFalse(any("murkman" in value for value in identifiers))

    def test_complex_rule_exposes_engine_relevant_facts(self):
        feature = next(item for item in self.bundle["features"]
                       if item["id"] == "path.sorcier.cryomancien.rank-4.active")
        facts = feature["resolution"]["facts"]
        self.assertIn("damage", facts["mechanics"])
        self.assertIn("dexterity", [item["ability"] for item in facts["saving_throws"]])

    def feature(self, feature_id):
        return next(item for item in self.bundle["features"] if item["id"] == feature_id)


if __name__ == "__main__":
    unittest.main()

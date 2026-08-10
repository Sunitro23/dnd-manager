import unittest

from dnd_manager.characters.common.rules import (
    ability_modifier,
    adjusted_health,
    defense,
    maximum_hp,
    point_buy_total,
    valid_point_buy,
)
from dnd_manager.shared.errors import InvalidRequest
from dnd_manager.campaign.path_schema import describe_capability


class RulesTestCase(unittest.TestCase):
    def test_ability_modifiers_use_floor_division(self):
        self.assertEqual(ability_modifier(8), -1)
        self.assertEqual(ability_modifier(10), 0)
        self.assertEqual(ability_modifier(13), 1)
        self.assertEqual(ability_modifier(15), 2)

    def test_point_buy_requires_six_scores_costing_27(self):
        scores = (15, 15, 13, 10, 10, 8)
        self.assertEqual(point_buy_total(scores), 27)
        self.assertTrue(valid_point_buy(scores))
        self.assertFalse(valid_point_buy((15, 15, 13, 10, 10, 9)))

    def test_point_buy_accepts_extended_range_and_rejects_above_it(self):
        self.assertEqual(point_buy_total((16, 8, 8, 8, 8, 8)), 11)
        with self.assertRaises(InvalidRequest):
            point_buy_total((21, 8, 8, 8, 8, 8))

    def test_maximum_hp_rejects_an_unknown_hit_die(self):
        with self.assertRaises(InvalidRequest):
            maximum_hp(hit_die=7, level=1, constitution=10)

    def test_adjusted_health_rejects_a_non_positive_maximum(self):
        with self.assertRaises(InvalidRequest):
            adjusted_health(10, 20, 0)

    def test_fixed_maximum_hp(self):
        self.assertEqual(maximum_hp(hit_die=8, level=1, constitution=14), 10)
        self.assertEqual(maximum_hp(hit_die=8, level=2, constitution=14), 17)
        self.assertEqual(maximum_hp(hit_die=8, level=2, constitution=16), 19)

    def test_current_hp_follows_max_only_when_full(self):
        self.assertEqual(adjusted_health(20, 20, 25), 25)
        self.assertEqual(adjusted_health(12, 20, 25), 12)
        self.assertEqual(adjusted_health(18, 20, 15), 15)

    def test_defense_adds_equipped_bonuses(self):
        self.assertEqual(defense(14, (2, -1, 3)), 6)

    def test_manual_effect_uses_the_gm_description_without_technical_text(self):
        description = describe_capability({
            "targeting": {"selector": "self"},
            "operations": [{"type": "custom_ability", "target": "self",
                            "description": "Traverse les miroirs proches."}],
        })
        self.assertEqual(description, "Traverse les miroirs proches.")
        self.assertNotIn("effet manuel", description)

    def test_choice_lists_every_option(self):
        description = describe_capability({
            "targeting": {"selector": "self"},
            "operations": [{"type": "choice", "target": "self",
                            "options": ["Gagner 2 Défenses", "Se déplacer de 3 m"]}],
        })
        self.assertIn("Gagner 2 Défenses", description)
        self.assertIn("Se déplacer de 3 m", description)

    def test_area_effects_are_conjugated_in_the_plural(self):
        description = describe_capability({
            "targeting": {"selector": "all"},
            "operations": [{"type": "modify_resource", "operation": "add",
                            "resource": "health", "value": 4}],
        })
        self.assertIn("Les cibles dans la zone récupèrent 4 PV", description)

    def test_plural_effects_agree_verbs_and_possessives(self):
        capability = {
            "targeting": {"selector": "multiple"},
            "operations": [{"type": "modify_stat", "target": "selected",
                            "stat": "defense.spiritual", "operation": "add", "value": 1}],
        }
        self.assertEqual(
            describe_capability(capability),
            "Les cibles augmentent leur Défense spirituelle de +1.",
        )

    def test_operation_target_reference_and_subtraction_drive_the_description(self):
        description = describe_capability({
            "targeting": {"selector": "single", "allegiance": ["enemy"]},
            "operations": [{
                "type": "modify_stat", "target": "selected",
                "target_ref": "target.primary", "stat": "movement.walk",
                "operation": "subtract", "value": 3,
                "duration": {"value": 2, "unit": "turn"},
            }],
        })
        self.assertEqual(
            description,
            "La cible principale réduit sa vitesse de déplacement à pied de 3 m "
            "pendant 2 tours de l’utilisateur.",
        )


if __name__ == "__main__":
    unittest.main()

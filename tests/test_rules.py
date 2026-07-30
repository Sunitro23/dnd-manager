import unittest

from dnd_manager.characters.common.rules import (
    ability_modifier,
    adjusted_current_hp,
    defense,
    maximum_hp,
    point_buy_total,
    valid_point_buy,
)


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
        with self.assertRaises(ValueError):
            point_buy_total((21, 8, 8, 8, 8, 8))

    def test_fixed_maximum_hp(self):
        self.assertEqual(maximum_hp(hit_die=8, level=1, constitution=14), 10)
        self.assertEqual(maximum_hp(hit_die=8, level=2, constitution=14), 17)
        self.assertEqual(maximum_hp(hit_die=8, level=2, constitution=16), 19)

    def test_current_hp_follows_max_only_when_full(self):
        self.assertEqual(adjusted_current_hp(20, 20, 25), 25)
        self.assertEqual(adjusted_current_hp(12, 20, 25), 12)
        self.assertEqual(adjusted_current_hp(18, 20, 15), 15)

    def test_defense_adds_equipped_bonuses(self):
        self.assertEqual(defense(14, (2, -1, 3)), 6)


if __name__ == "__main__":
    unittest.main()

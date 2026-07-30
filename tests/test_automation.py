import unittest

from dnd_manager.automation.compiler import compile_effect
from dnd_manager.automation.contracts import ResolutionContext, TargetState
from dnd_manager.automation.resolver import resolve
from dnd_manager.shared.errors import InvalidRequest


class FixedRoller:
    def __init__(self, value):
        self.value = value

    def roll(self, count, sides):
        return self.value


class AutomationTestCase(unittest.TestCase):
    def test_healing_uses_dice_and_ability_modifier(self):
        context = ResolutionContext(FixedRoller(9), (("constitution", 3),))
        result = resolve((healing_spec(),), TargetState("hero", 4, 20), context)
        self.assertEqual(result.target.hit_points, 16)
        self.assertEqual(result.events[0].amount, 12)

    def test_healing_cannot_exceed_maximum(self):
        context = ResolutionContext(FixedRoller(12))
        result = resolve((healing_spec(),), TargetState("hero", 18, 20), context)
        self.assertEqual(result.target.hit_points, 20)
        self.assertEqual(result.events[0].amount, 2)

    def test_damage_cannot_make_hit_points_negative(self):
        context = ResolutionContext(FixedRoller(12))
        result = resolve((damage_spec(),), TargetState("enemy", 5, 20), context)
        self.assertEqual(result.target.hit_points, 0)
        self.assertEqual(result.events[0].amount, 5)

    def test_unknown_effect_is_rejected(self):
        with self.assertRaises(InvalidRequest):
            compile_effect({"type": "teleport", "value": {"dice": {"count": 1, "sides": 6}}})


def healing_spec():
    return {"type": "heal", "target": "self", "value": {"dice": {"count": 2, "sides": 8},
                                                            "ability_modifier": "constitution"}}


def damage_spec():
    return {"type": "deal_damage", "target": "self",
            "value": {"dice": {"count": 3, "sides": 6}}}


if __name__ == "__main__":
    unittest.main()

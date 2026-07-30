import unittest

from dnd_manager.automation.compiler import compile_effect
from dnd_manager.characters.progression import (
    ActionCommand,
    ChooseRacialBonus,
    RaiseLevel,
    RankCommand,
    RacialBonusCommand,
    UnlockRank,
    UseAction,
)
from dnd_manager.characters.progression.contracts import (
    ActionState,
    ProgressionState,
    RacialBonusState,
    RankState,
)
from dnd_manager.shared.errors import InvalidRequest, ResourceNotFound


class FixedRoller:
    def __init__(self, value):
        self.value = value

    def roll(self, count, sides):
        return self.value


class MemoryProgressionRepository:
    def __init__(self, state):
        self.state = state
        self.saved = None

    def find(self, character_id, public_only):
        return self.state

    def save_level(self, state, result):
        self.saved = result

    def find_rank(self, character_id, public_only, command):
        return self.state

    def save_rank(self, state, result):
        self.saved = result

    def find_action(self, character_id, public_only, command):
        return self.state

    def save_action(self, state, result):
        self.saved = result

    def find_racial_bonus(self, character_id, public_only, command):
        return self.state

    def save_racial_bonus(self, state, result):
        self.saved = result


class ProgressionTestCase(unittest.TestCase):
    def test_level_calculation_is_independent_from_storage(self):
        state = ProgressionState(4, 1, 12, 12, 15, 8, 0, 2)
        repository = MemoryProgressionRepository(state)
        result = RaiseLevel(repository).execute(4, True)
        self.assertEqual((result.level, result.current_hp, result.maximum_hp), (2, 17, 17))
        self.assertIs(repository.saved, result)

    def test_wounded_character_keeps_current_health(self):
        state = ProgressionState(4, 1, 7, 12, 15, 8, 0, 2)
        result = RaiseLevel(MemoryProgressionRepository(state)).execute(4, True)
        self.assertEqual(result.current_hp, 7)

    def test_maximum_level_fails_before_saving(self):
        repository = MemoryProgressionRepository(ProgressionState(4, 20, 12, 12, 15, 8, 0, 2))
        with self.assertRaises(InvalidRequest):
            RaiseLevel(repository).execute(4, True)
        self.assertIsNone(repository.saved)

    def test_missing_character_is_an_expected_failure(self):
        with self.assertRaises(ResourceNotFound):
            RaiseLevel(MemoryProgressionRepository(None)).execute(4, True)

    def test_next_rank_uses_stable_contracts(self):
        repository = MemoryProgressionRepository(RankState(4, 3, 1, 2, True))
        result = UnlockRank(repository).execute(4, True, RankCommand("class", 9))
        self.assertEqual((result.path_id, result.rank), (9, 2))
        self.assertIs(repository.saved, result)

    def test_rank_is_rejected_when_points_are_spent(self):
        repository = MemoryProgressionRepository(RankState(4, 2, 2, 1, True))
        with self.assertRaises(InvalidRequest):
            UnlockRank(repository).execute(4, True, RankCommand("racial", 9))
        self.assertIsNone(repository.saved)

    def test_unknown_path_type_fails_before_repository_access(self):
        repository = MemoryProgressionRepository(RankState(4, 2, 0, 1, True))
        with self.assertRaises(InvalidRequest):
            UnlockRank(repository).execute(4, True, RankCommand("unknown", 9))
        self.assertIsNone(repository.saved)

    def test_limited_action_reports_remaining_uses(self):
        repository = MemoryProgressionRepository(ActionState(4, "Parade", "2 fois", 1, True))
        command = ActionCommand("class", 9, 1)
        result = UseAction(repository).execute(4, True, command)
        self.assertEqual((result.name, result.remaining), ("Parade", 0))
        self.assertIs(repository.saved, result)

    def test_automated_action_updates_health_before_saving(self):
        effect = compile_effect({"type": "heal", "value": {"dice": {"count": 2, "sides": 8},
                                                           "ability_modifier": "constitution"}})
        state = ActionState(4, "Rappel des os", "2 fois", 0, True, 2, 3, 20,
                            (("constitution", 2),), (effect,))
        repository = MemoryProgressionRepository(state)
        result = UseAction(repository, FixedRoller(8)).execute(
            4, True, ActionCommand("racial", 9, 2))
        self.assertEqual((result.current_hp, result.automated), (13, True))
        self.assertIs(repository.saved, result)

    def test_exhausted_action_fails_without_writing(self):
        repository = MemoryProgressionRepository(ActionState(4, "Parade", "2 fois", 2, True))
        with self.assertRaises(InvalidRequest):
            UseAction(repository).execute(4, True, ActionCommand("class", 9, 1))
        self.assertIsNone(repository.saved)

    def test_passive_rank_cannot_be_spent(self):
        repository = MemoryProgressionRepository(ActionState(4, "Endurance", "", 0, True))
        with self.assertRaises(InvalidRequest):
            UseAction(repository).execute(4, True, ActionCommand("class", 9, 1))
        self.assertIsNone(repository.saved)

    def test_racial_bonus_recalculates_health(self):
        state = RacialBonusState(4, "Sang ancien", 2, 17, 17, 15, 8, 2, 3, True, True)
        repository = MemoryProgressionRepository(state)
        result = ChooseRacialBonus(repository).execute(4, True, RacialBonusCommand(9))
        self.assertEqual((result.path_name, result.maximum_hp), ("Sang ancien", 19))
        self.assertEqual(result.current_hp, 19)
        self.assertIs(repository.saved, result)

    def test_racial_bonus_requires_first_rank(self):
        state = RacialBonusState(4, "Sang ancien", 2, 17, 17, 15, 8, 2, 3, True, False)
        repository = MemoryProgressionRepository(state)
        with self.assertRaises(InvalidRequest):
            ChooseRacialBonus(repository).execute(4, True, RacialBonusCommand(9))
        self.assertIsNone(repository.saved)


if __name__ == "__main__":
    unittest.main()

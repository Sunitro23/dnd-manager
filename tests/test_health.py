import unittest

from dnd_manager.characters.health import ChangeHealth, HealthCommand
from dnd_manager.characters.health.contracts import HealthState
from dnd_manager.shared.errors import InvalidRequest, ResourceNotFound


class MemoryHealthRepository:
    def __init__(self, state):
        self.state = state
        self.saved = None

    def find(self, character_id, public_only):
        return self.state

    def save(self, state, result):
        self.saved = result


class HealthTestCase(unittest.TestCase):
    def test_use_case_depends_only_on_repository_contract(self):
        repository = MemoryHealthRepository(HealthState(7, 8, 12, True, 3))
        result = ChangeHealth(repository).execute(7, True, HealthCommand("heal", "3"))
        self.assertEqual(result.current, 11)
        self.assertIs(repository.saved, result)

    def test_missing_character_is_an_expected_failure(self):
        service = ChangeHealth(MemoryHealthRepository(None))
        with self.assertRaises(ResourceNotFound):
            service.execute(7, True, HealthCommand("heal", "3"))

    def test_invalid_command_does_not_modify_repository(self):
        repository = MemoryHealthRepository(HealthState(7, 8, 12, True, 3))
        with self.assertRaises(InvalidRequest):
            ChangeHealth(repository).execute(7, True, HealthCommand("unknown"))
        self.assertIsNone(repository.saved)


if __name__ == "__main__":
    unittest.main()

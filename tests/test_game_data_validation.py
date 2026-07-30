import json
import unittest
from copy import deepcopy
from pathlib import Path

from dnd_manager.configuration.validation import validate_config
from dnd_manager.shared.errors import InvalidRequest


class GameDataValidationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(Path("game_data.json").read_text(encoding="utf-8"))

    def test_current_game_data_is_valid(self):
        self.assertIsNotNone(validate_config(deepcopy(self.config))["classes"])

    def test_duplicate_identifier_is_rejected(self):
        config = deepcopy(self.config)
        config["classes"][1]["id"] = config["classes"][0]["id"]
        with self.assertRaises(InvalidRequest):
            validate_config(config)

    def test_invalid_rank_sequence_is_rejected(self):
        config = deepcopy(self.config)
        config["classes"][0]["paths"][0]["ranks"][0]["rank"] = 2
        with self.assertRaises(InvalidRequest):
            validate_config(config)

    def test_invalid_automated_effect_is_rejected(self):
        config = deepcopy(self.config)
        active = find_rank(
            config, "path.enfant-des-tenebres.enfant-de-la-mort.rank-2"
        )["active"]
        active["automation"]["effects"][0]["value"]["dice"]["sides"] = 0
        with self.assertRaises(InvalidRequest):
            validate_config(config)

    def test_bonfire_rest_identifier_is_rejected(self):
        config = deepcopy(self.config)
        active = find_rank(
            config, "path.enfant-des-tenebres.enfant-de-la-mort.rank-2"
        )["active"]
        active["resource"]["recovery"] = ["bonfire_rest"]
        with self.assertRaises(InvalidRequest):
            validate_config(config)


def find_rank(config, identifier):
    ranks = (rank for race in config["races"] for path in race["paths"] for rank in path["ranks"])
    return next(rank for rank in ranks if rank["id"] == identifier)


if __name__ == "__main__":
    unittest.main()

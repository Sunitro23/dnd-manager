import unittest

from dnd_manager.characters.inventory import (
    ConsumeCommand,
    ConsumeItem,
    DeleteCommand,
    DeleteItem,
    DuplicateCommand,
    DuplicateItem,
    QuickCreateCommand,
    QuickCreateItem,
    ToggleCommand,
    ToggleItem,
)
from dnd_manager.characters.inventory.contracts import (
    ItemState,
    DuplicateResult,
    ItemCopy,
    QuickCreateResult,
    ToggleState,
)
from dnd_manager.shared.errors import InvalidRequest, ResourceNotFound


class MemoryInventoryRepository:
    def __init__(self, state):
        self.state = state
        self.saved = None

    def find_item(self, character_id, public_only, command):
        return self.state

    def save_consumption(self, state, result):
        self.saved = result

    def find_toggle(self, character_id, public_only, command):
        return self.state

    def save_toggle(self, state, result):
        self.saved = result

    def character_exists(self, character_id, public_only):
        return self.state is not None

    def create_quick_item(self, character_id, name, command):
        self.saved = QuickCreateResult(character_id, 12, name, command.item_type)
        return self.saved

    def find_delete(self, character_id, public_only, command):
        return self.state

    def save_delete(self, state, result):
        self.saved = result

    def find_copy(self, character_id, public_only, command):
        return self.state

    def save_copy(self, item):
        self.saved = DuplicateResult(item.character_id, 13, item.name)
        return self.saved


class InventoryTestCase(unittest.TestCase):
    def test_consumption_decrements_stable_item_contract(self):
        repository = MemoryInventoryRepository(ItemState(4, 8, "Fiole", "consumable", 2))
        result = ConsumeItem(repository).execute(4, True, ConsumeCommand(8))
        self.assertEqual((result.name, result.remaining), ("Fiole", 1))
        self.assertIs(repository.saved, result)

    def test_non_consumable_is_rejected_without_writing(self):
        repository = MemoryInventoryRepository(ItemState(4, 8, "Épée", "weapon", 1))
        with self.assertRaises(InvalidRequest):
            ConsumeItem(repository).execute(4, True, ConsumeCommand(8))
        self.assertIsNone(repository.saved)

    def test_missing_item_is_an_expected_failure(self):
        with self.assertRaises(ResourceNotFound):
            ConsumeItem(MemoryInventoryRepository(None)).execute(4, True, ConsumeCommand(8))

    def test_weapon_uses_first_available_hand(self):
        state = toggle_state(item_type="weapon", occupied_slots=("right_hand",))
        repository = MemoryInventoryRepository(state)
        result = ToggleItem(repository).execute(4, True, ToggleCommand(8))
        self.assertEqual((result.equipped, result.slot), (True, "left_hand"))
        self.assertIs(repository.saved, result)

    def test_full_slot_group_is_rejected(self):
        state = toggle_state(item_type="armor", occupied_slots=("armor",))
        repository = MemoryInventoryRepository(state)
        with self.assertRaises(InvalidRequest):
            ToggleItem(repository).execute(4, True, ToggleCommand(8))
        self.assertIsNone(repository.saved)

    def test_constitution_accessory_recalculates_health(self):
        state = toggle_state(item_type="accessory", item_stat="CON", item_stat_bonus=2)
        result = ToggleItem(MemoryInventoryRepository(state)).execute(4, True, ToggleCommand(8))
        self.assertEqual((result.current_hp, result.maximum_hp), (19, 19))

    def test_quick_creation_uses_domain_label(self):
        repository = MemoryInventoryRepository(object())
        result = QuickCreateItem(repository).execute(4, True, QuickCreateCommand("spell"))
        self.assertEqual((result.name, result.item_type), ("Nouveau sort", "spell"))

    def test_unknown_quick_type_fails_before_storage(self):
        repository = MemoryInventoryRepository(object())
        with self.assertRaises(InvalidRequest):
            QuickCreateItem(repository).execute(4, True, QuickCreateCommand("unknown"))
        self.assertIsNone(repository.saved)

    def test_deleting_equipped_constitution_item_updates_health(self):
        state = toggle_state(item_type="accessory", equipped=True, slot="ring_1",
                             item_stat="CON", item_stat_bonus=2,
                             constitution_bonus=2, current_hp=19, maximum_hp=19)
        repository = MemoryInventoryRepository(state)
        result = DeleteItem(repository).execute(4, True, DeleteCommand(8))
        self.assertEqual((result.current_hp, result.maximum_hp), (17, 17))
        self.assertIs(repository.saved, result)

    def test_duplicate_is_unequipped_copy_with_explicit_contract(self):
        item = ItemCopy(4, "Épée", "weapon", 1, 0, 0, 0, "1d8", "physical",
                        "", "", 0, "", "", "")
        repository = MemoryInventoryRepository(item)
        result = DuplicateItem(repository).execute(4, True, DuplicateCommand(8))
        self.assertEqual((result.name, result.equipment_id), ("Épée — copie", 13))


def toggle_state(**changes):
    values = {
        "character_id": 4, "equipment_id": 8, "item_type": "weapon",
        "equipped": False, "slot": "", "occupied_slots": (), "level": 2,
        "constitution": 15, "constitution_bonus": 0, "item_stat": "",
        "item_stat_bonus": 0, "hit_die": 8, "current_hp": 17,
        "maximum_hp": 17, "version": 3,
    }
    values.update(changes)
    return ToggleState(**values)


if __name__ == "__main__":
    unittest.main()

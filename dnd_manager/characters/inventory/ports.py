from typing import Protocol

from dnd_manager.characters.inventory.contracts import (
    ConsumeCommand,
    ConsumeResult,
    ItemState,
    ToggleCommand,
    ToggleResult,
    ToggleState,
    QuickCreateCommand,
    QuickCreateResult,
    DeleteCommand,
    DeleteResult,
    DuplicateCommand,
    DuplicateResult,
    ItemCopy,
    SaveItemCommand,
    SaveItemResult,
)


class InventoryRepository(Protocol):
    def find_item(self, character_id: int, public_only: bool,
                  command: ConsumeCommand) -> ItemState | None: ...

    def save_consumption(self, state: ItemState, result: ConsumeResult) -> None: ...

    def find_toggle(self, character_id: int, public_only: bool,
                    command: ToggleCommand) -> ToggleState | None: ...

    def save_toggle(self, state: ToggleState, result: ToggleResult) -> None: ...

    def character_exists(self, character_id: int, public_only: bool) -> bool: ...

    def create_quick_item(self, character_id: int, name: str,
                          command: QuickCreateCommand) -> QuickCreateResult: ...

    def find_delete(self, character_id: int, public_only: bool,
                    command: DeleteCommand) -> ToggleState | None: ...

    def save_delete(self, state: ToggleState, result: DeleteResult) -> None: ...

    def find_copy(self, character_id: int, public_only: bool,
                  command: DuplicateCommand) -> ItemCopy | None: ...

    def save_copy(self, item: ItemCopy) -> DuplicateResult: ...

    def save_item(self, character_id: int, command: SaveItemCommand) -> SaveItemResult: ...

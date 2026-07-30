from dnd_manager.characters.inventory.domain import (
    consume,
    delete_item,
    duplicate_item,
    quick_item_name,
    toggle,
)
from dnd_manager.shared.errors import ResourceNotFound


class ConsumeItem:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        state = self.repository.find_item(character_id, public_only, command)
        return self.consume_found(state)

    def consume_found(self, state):
        if state is None:
            raise ResourceNotFound("Objet introuvable.")
        result = consume(state)
        self.repository.save_consumption(state, result)
        return result


class ToggleItem:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        state = self.repository.find_toggle(character_id, public_only, command)
        return self.toggle_found(state)

    def toggle_found(self, state):
        if state is None:
            raise ResourceNotFound("Objet introuvable.")
        result = toggle(state)
        self.repository.save_toggle(state, result)
        return result


class QuickCreateItem:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        name = quick_item_name(command.item_type)
        return self.create_for_character(character_id, public_only, command, name)

    def create_for_character(self, character_id, public_only, command, name):
        if not self.repository.character_exists(character_id, public_only):
            raise ResourceNotFound("Personnage introuvable.")
        return self.repository.create_quick_item(character_id, name, command)


class DeleteItem:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        state = self.repository.find_delete(character_id, public_only, command)
        return self.delete_found(state)

    def delete_found(self, state):
        if state is None:
            raise ResourceNotFound("Objet introuvable.")
        result = delete_item(state)
        self.repository.save_delete(state, result)
        return result


class DuplicateItem:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        item = self.repository.find_copy(character_id, public_only, command)
        return self.copy_found(item)

    def copy_found(self, item):
        if item is None:
            raise ResourceNotFound("Objet introuvable.")
        return self.repository.save_copy(duplicate_item(item))


class SaveItem:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        if not self.repository.character_exists(character_id, public_only):
            raise ResourceNotFound("Personnage introuvable.")
        return self.repository.save_item(character_id, command)

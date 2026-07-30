from dnd_manager.characters.health.domain import health_result
from dnd_manager.shared.errors import ResourceNotFound


class ChangeHealth:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        state = self.repository.find(character_id, public_only)
        return self.apply(state, command)

    def apply(self, state, command):
        if state is None:
            raise ResourceNotFound("Personnage introuvable.")
        result = health_result(state, command)
        self.repository.save(state, result)
        return result

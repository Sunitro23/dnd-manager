from dnd_manager.shared.errors import InvalidRequest, ResourceNotFound


class ReadCharacter:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id):
        snapshot = self.repository.find(character_id)
        if snapshot is None:
            raise ResourceNotFound("Personnage introuvable.")
        return snapshot


class ListCharacters:
    def __init__(self, repository):
        self.repository = repository

    def execute(self):
        return self.repository.list()


class SyncCharacterHealth:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, command):
        validate_health(command)
        result = self.repository.sync_health(character_id, command)
        if result is None:
            raise ResourceNotFound("Personnage introuvable.")
        return result


class SyncCharacterResource:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, resource_key, command):
        resource = find_resource(self.repository.find(character_id), resource_key)
        validate_resource(command, resource)
        return self.repository.sync_resource(character_id, resource_key, command)


def find_resource(snapshot, resource_key):
    if snapshot is None:
        raise ResourceNotFound("Personnage introuvable.")
    resource = next((value for value in snapshot.resources if value.key == resource_key), None)
    if resource is None:
        raise ResourceNotFound("Ressource introuvable.")
    return resource


def validate_resource(command, resource):
    validate_version(command.expected_version)
    if command.spent < 0 or command.spent > resource.maximum:
        raise InvalidRequest("La dépense de ressource est invalide.")


def validate_health(command):
    validate_version(command.expected_version)
    if command.current_hp < 0:
        raise InvalidRequest("Les PV ne peuvent pas être négatifs.")


def validate_version(version):
    if version < 1:
        raise InvalidRequest("La version attendue est invalide.")

from typing import Protocol

from dnd_manager.character_api.contracts import (
    CharacterReference,
    CharacterSnapshot,
    HealthSyncCommand,
    HealthSyncResult,
    ResourceSyncCommand,
    ResourceSyncResult,
)


class CharacterExchangeRepository(Protocol):
    def list(self) -> tuple[CharacterReference, ...]: ...

    def find(self, character_id: int) -> CharacterSnapshot | None: ...

    def sync_health(self, character_id: int, command: HealthSyncCommand) -> HealthSyncResult | None: ...

    def sync_resource(self, character_id: int, resource_key: str,
                      command: ResourceSyncCommand) -> ResourceSyncResult | None: ...

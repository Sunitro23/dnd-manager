from typing import Protocol

from dnd_manager.characters.health.contracts import HealthResult, HealthState


class HealthRepository(Protocol):
    def find(self, character_id: int, public_only: bool) -> HealthState | None: ...

    def save(self, state: HealthState, result: HealthResult) -> None: ...

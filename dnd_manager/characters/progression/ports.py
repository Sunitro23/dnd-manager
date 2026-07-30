from typing import Protocol

from dnd_manager.characters.progression.contracts import (
    ActionCommand,
    ActionResult,
    ActionState,
    LevelResult,
    ProgressionState,
    RankCommand,
    RankResult,
    RankState,
    RacialBonusCommand,
    RacialBonusResult,
    RacialBonusState,
)


class ProgressionRepository(Protocol):
    def find(self, character_id: int, public_only: bool) -> ProgressionState | None: ...

    def save_level(self, state: ProgressionState, result: LevelResult) -> None: ...

    def find_rank(self, character_id: int, public_only: bool,
                  command: RankCommand) -> RankState | None: ...

    def save_rank(self, state: RankState, result: RankResult) -> None: ...

    def find_action(self, character_id: int, public_only: bool,
                    command: ActionCommand) -> ActionState | None: ...

    def save_action(self, state: ActionState, result: ActionResult) -> None: ...

    def find_racial_bonus(self, character_id: int, public_only: bool,
                          command: RacialBonusCommand) -> RacialBonusState | None: ...

    def save_racial_bonus(self, state: RacialBonusState,
                          result: RacialBonusResult) -> None: ...

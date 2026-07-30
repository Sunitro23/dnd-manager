from dataclasses import dataclass
from typing import Protocol


class DiceRoller(Protocol):
    def roll(self, count: int, sides: int) -> int: ...


@dataclass(frozen=True)
class Dice:
    count: int
    sides: int


@dataclass(frozen=True)
class Formula:
    dice: Dice
    modifier: str | None = None
    bonus: int = 0


@dataclass(frozen=True)
class TargetState:
    identifier: str
    hit_points: int
    maximum_hit_points: int


@dataclass(frozen=True)
class ResolutionContext:
    roller: DiceRoller
    ability_modifiers: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class EffectEvent:
    effect_type: str
    target_id: str
    amount: int


@dataclass(frozen=True)
class Resolution:
    target: TargetState
    events: tuple[EffectEvent, ...]

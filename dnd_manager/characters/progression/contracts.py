from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressionState:
    character_id: int
    level: int
    current_hp: int
    maximum_hp: int
    constitution: int
    hit_die: int
    constitution_bonus: int
    version: int


@dataclass(frozen=True)
class LevelResult:
    character_id: int
    level: int
    current_hp: int
    maximum_hp: int


@dataclass(frozen=True)
class RankCommand:
    path_type: str
    path_id: int


@dataclass(frozen=True)
class RankState:
    character_id: int
    level: int
    spent_points: int
    next_rank: int
    path_available: bool


@dataclass(frozen=True)
class RankResult:
    character_id: int
    path_type: str
    path_id: int
    rank: int


@dataclass(frozen=True)
class ActionCommand:
    path_type: str
    path_id: int
    rank: int


@dataclass(frozen=True)
class ActionState:
    character_id: int
    name: str
    uses: str
    spent: int
    unlocked: bool
    limit: int | None = None
    current_hp: int = 0
    maximum_hp: int = 0
    ability_modifiers: tuple[tuple[str, int], ...] = ()
    effects: tuple[object, ...] = ()


@dataclass(frozen=True)
class ActionResult:
    character_id: int
    path_type: str
    path_id: int
    rank: int
    name: str
    remaining: int
    current_hp: int = 0
    maximum_hp: int = 0
    automated: bool = False


@dataclass(frozen=True)
class RacialBonusCommand:
    path_id: int


@dataclass(frozen=True)
class RacialBonusState:
    character_id: int
    path_name: str
    level: int
    current_hp: int
    maximum_hp: int
    constitution: int
    hit_die: int
    constitution_bonus: int
    version: int
    path_available: bool
    rank_unlocked: bool


@dataclass(frozen=True)
class RacialBonusResult:
    character_id: int
    path_id: int
    path_name: str
    current_hp: int
    maximum_hp: int

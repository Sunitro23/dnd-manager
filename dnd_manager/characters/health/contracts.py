from dataclasses import dataclass


@dataclass(frozen=True)
class HealthCommand:
    action: str
    amount: str = ""
    defense: str = "0"


@dataclass(frozen=True)
class HealthState:
    character_id: int
    current: int
    maximum: int
    estus_available: bool
    version: int


@dataclass(frozen=True)
class HealthResult:
    character_id: int
    previous: int
    current: int
    maximum: int
    estus_available: bool
    refresh_sheet: bool

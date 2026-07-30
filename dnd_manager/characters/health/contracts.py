from dataclasses import dataclass


@dataclass(frozen=True)
class HealthCommand:
    action: str
    amount: str = ""
    damage_type: str = "physical"


@dataclass(frozen=True)
class HealthState:
    character_id: int
    current: int
    maximum: int
    estus_available: bool
    version: int
    # Défenses résolues côté serveur : le client ne les fournit plus.
    defenses: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class HealthResult:
    character_id: int
    previous: int
    current: int
    maximum: int
    estus_available: bool
    refresh_sheet: bool

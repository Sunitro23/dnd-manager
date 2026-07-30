from dataclasses import dataclass


@dataclass(frozen=True)
class AbilityValue:
    key: str
    score: int
    modifier: int


@dataclass(frozen=True)
class ResourceValue:
    key: str
    name: str
    spent: int
    maximum: int


@dataclass(frozen=True)
class CharacterReference:
    character_id: int
    version: int
    name: str
    character_type: str


@dataclass(frozen=True)
class DefenseValue:
    key: str
    value: int


@dataclass(frozen=True)
class DiceValue:
    count: int
    sides: int


@dataclass(frozen=True)
class EquipmentValue:
    equipment_id: int
    name: str
    item_type: str
    quantity: int
    slot: str
    damage: DiceValue | None
    damage_expression: str
    damage_type: str | None
    defense_bonuses: tuple[DefenseValue, ...]
    ability: str | None
    ability_bonus: int
    effect_text: str


@dataclass(frozen=True)
class CharacterSnapshot:
    character_id: int
    version: int
    name: str
    character_type: str
    level: int
    class_id: str
    species_id: str
    class_path_id: str | None
    racial_path_id: str | None
    size: str | None
    speed: int | None
    current_hp: int
    maximum_hp: int
    abilities: tuple[AbilityValue, ...]
    base_defenses: tuple[DefenseValue, ...]
    equipment: tuple[EquipmentValue, ...]
    feature_ids: tuple[str, ...]
    resources: tuple[ResourceValue, ...]


@dataclass(frozen=True)
class HealthSyncCommand:
    current_hp: int
    expected_version: int


@dataclass(frozen=True)
class HealthSyncResult:
    character_id: int
    version: int
    current_hp: int
    maximum_hp: int


@dataclass(frozen=True)
class ResourceSyncCommand:
    spent: int
    expected_version: int


@dataclass(frozen=True)
class ResourceSyncResult:
    character_id: int
    version: int
    resource: ResourceValue

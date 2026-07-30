from dataclasses import dataclass, fields


@dataclass(frozen=True)
class ConsumeCommand:
    equipment_id: int


@dataclass(frozen=True)
class ItemState:
    character_id: int
    equipment_id: int
    name: str
    item_type: str
    quantity: int


@dataclass(frozen=True)
class ConsumeResult:
    character_id: int
    equipment_id: int
    name: str
    remaining: int


@dataclass(frozen=True)
class ToggleCommand:
    equipment_id: int


@dataclass(frozen=True)
class ToggleState:
    character_id: int
    equipment_id: int
    item_type: str
    equipped: bool
    slot: str
    occupied_slots: tuple[str, ...]
    level: int
    constitution: int
    constitution_bonus: int
    item_stat: str
    item_stat_bonus: int
    hit_die: int
    current_hp: int
    maximum_hp: int
    version: int


@dataclass(frozen=True)
class ToggleResult:
    character_id: int
    equipment_id: int
    equipped: bool
    slot: str
    current_hp: int
    maximum_hp: int


@dataclass(frozen=True)
class QuickCreateCommand:
    item_type: str


@dataclass(frozen=True)
class QuickCreateResult:
    character_id: int
    equipment_id: int
    name: str
    item_type: str


@dataclass(frozen=True)
class DeleteCommand:
    equipment_id: int


@dataclass(frozen=True)
class DeleteResult:
    character_id: int
    equipment_id: int
    current_hp: int
    maximum_hp: int


@dataclass(frozen=True)
class DuplicateCommand:
    equipment_id: int


@dataclass(frozen=True)
class ItemCopy:
    character_id: int
    name: str
    item_type: str
    quantity: int
    physical_bonus: int
    elemental_bonus: int
    spiritual_bonus: int
    damage_dice: str
    damage_type: str
    uses: str
    stat: str
    stat_bonus: int
    icon_path: str
    effect: str
    notes: str


@dataclass(frozen=True)
class DuplicateResult:
    character_id: int
    equipment_id: int
    name: str


@dataclass(frozen=True)
class ItemData:
    name: str
    item_type: str
    quantity: int
    equipped: int
    physical_bonus: int
    elemental_bonus: int
    spiritual_bonus: int
    damage_dice: str
    damage_type: str
    uses: str
    stat: str
    stat_bonus: int
    icon_path: str
    effect: str
    notes: str


@dataclass(frozen=True)
class SaveItemCommand:
    data: ItemData
    equipment_id: int | None = None


@dataclass(frozen=True)
class SaveItemResult:
    character_id: int
    equipment_id: int


ITEM_FIELDS = tuple(field.name for field in fields(ItemData))
"""Colonnes de données d'un objet, dérivées du contrat pour interdire toute dérive."""

EQUIPMENT_COLUMNS = ITEM_FIELDS + ("slot",)
"""Toutes les colonnes à recopier lorsqu'un inventaire est cloné."""


@dataclass(frozen=True)
class EquipmentView:
    id: int
    character_id: int
    name: str
    item_type: str
    quantity: int
    equipped: int
    physical_bonus: int
    elemental_bonus: int
    spiritual_bonus: int
    damage_dice: str
    damage_type: str
    uses: str
    stat: str
    stat_bonus: int
    slot: str
    icon_path: str
    effect: str
    notes: str

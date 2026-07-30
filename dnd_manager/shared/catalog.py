"""Vocabulaire partagé par toutes les capacités.

Ces listes étaient recopiées dans quatre à six modules chacune (et jusque dans les
templates), ce qui laissait dériver les valeurs entre le formulaire, la validation et
la base de données.
"""

CHARACTER_TYPES = ("player", "ally", "npc", "enemy")
VISIBILITIES = ("campaign", "gm")
ABILITY_FIELDS = ("strength", "dexterity", "constitution",
                  "intelligence", "wisdom", "charisma")
ABILITY_LABELS = {
    "strength": "Force", "dexterity": "Dextérité", "constitution": "Constitution",
    "intelligence": "Intelligence", "wisdom": "Sagesse", "charisma": "Charisme",
}
ABILITY_ABBREVIATIONS = {
    "FOR": "strength", "DEX": "dexterity", "CON": "constitution",
    "INT": "intelligence", "SAG": "wisdom", "CHA": "charisma",
}
ITEM_TYPES = ("weapon", "armor", "shield", "accessory", "tool",
              "consumable", "spell", "quest", "other")
EQUIPMENT_SLOTS = {
    "weapon": ("right_hand", "left_hand"),
    "shield": ("right_hand", "left_hand"),
    "tool": ("right_hand", "left_hand"),
    "armor": ("armor",),
    "accessory": ("ring_1", "ring_2", "ring_3", "ring_4"),
}
DAMAGE_TYPES = ("physical", "elemental", "spiritual")

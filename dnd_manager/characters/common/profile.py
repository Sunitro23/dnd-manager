"""Chargement du profil dérivé d'un personnage, sans dépendance à Flask.

La fiche web et le calcul des dégâts ont besoin des mêmes valeurs (scores effectifs,
objets équipés, bonus de voies, Défenses). Elles étaient auparavant assemblées
uniquement dans la couche de présentation, ce qui a conduit le formulaire de dégâts
à renvoyer la Défense au serveur dans un champ caché — donc à appliquer une valeur
potentiellement périmée.
"""

from dataclasses import dataclass

from dnd_manager.characters.common.rules import ability_modifier, defense
from dnd_manager.shared.catalog import ABILITY_ABBREVIATIONS, ABILITY_FIELDS
from dnd_manager.characters.inventory.sqlite_repository import equipment_for_character
from dnd_manager.paths.repository import paths_for_origin

DEFENSES = {
    "physical": ("Constitution", "constitution", "physical_bonus"),
    "elemental": ("Intelligence", "intelligence", "elemental_bonus"),
    "spiritual": ("Sagesse", "wisdom", "spiritual_bonus"),
}
DAMAGE_TYPES = tuple(DEFENSES)
CHARACTER_SQL = """
SELECT c.*, cc.name AS class_name, cc.hit_die,
       cc.strength_bonus AS class_strength_bonus,
       cc.dexterity_bonus AS class_dexterity_bonus,
       cc.constitution_bonus AS class_constitution_bonus,
       cc.intelligence_bonus AS class_intelligence_bonus,
       cc.wisdom_bonus AS class_wisdom_bonus,
       cc.charisma_bonus AS class_charisma_bonus,
       rp.name AS racial_bonus_name, rp.abilities AS racial_bonus_abilities,
       COALESCE(rp.strength_bonus, 0) AS racial_strength_bonus,
       COALESCE(rp.dexterity_bonus, 0) AS racial_dexterity_bonus,
       COALESCE(rp.constitution_bonus, 0) AS racial_constitution_bonus,
       COALESCE(rp.intelligence_bonus, 0) AS racial_intelligence_bonus,
       COALESCE(rp.wisdom_bonus, 0) AS racial_wisdom_bonus,
       COALESCE(rp.charisma_bonus, 0) AS racial_charisma_bonus,
       COALESCE(rp.physical_bonus, 0) AS path_physical_bonus,
       COALESCE(rp.elemental_bonus, 0) AS path_elemental_bonus,
       COALESCE(rp.spiritual_bonus, 0) AS path_spiritual_bonus,
       s.name AS species_name, s.description AS species_description,
       s.traits AS species_traits, s.size AS species_size, s.speed AS species_speed,
       s.physical_bonus AS species_physical_bonus,
       s.elemental_bonus AS species_elemental_bonus,
       s.spiritual_bonus AS species_spiritual_bonus, p.display_name AS owner_name
FROM character c
LEFT JOIN character_class cc ON cc.id = c.class_id
LEFT JOIN species s ON s.id = c.species_id
LEFT JOIN racial_path rp ON rp.id = c.racial_path_id
LEFT JOIN player p ON p.id = c.owner_id
WHERE c.id = ? AND (? = 1 OR c.visibility = 'campaign')
"""


@dataclass(frozen=True)
class CharacterProfile:
    character: object
    equipment: tuple
    equipped: tuple
    paths: tuple
    unlocked_rows: tuple
    unlocked_ranks: dict
    permanent_defense_bonuses: dict
    accessory_ability_bonuses: dict
    effective_scores: dict
    modifiers: dict
    defenses: dict


def load_profile(database, character_id, gm):
    character = load_character(database, character_id, gm)
    if character is None:
        return None
    return build_profile(database, character)


def build_profile(database, character):
    equipment = equipment_for_character(database, character["id"])
    equipped = tuple(item for item in equipment if item.equipped)
    progression = load_progression(database, character)
    abilities = ability_values(character, equipped)
    return assemble_profile(character, equipment, equipped, progression, abilities)


def assemble_profile(character, equipment, equipped, progression, abilities):
    return CharacterProfile(
        character=character, equipment=equipment, equipped=equipped,
        **progression, **abilities,
        defenses=defense_values(character, abilities["effective_scores"], equipped,
                                progression["permanent_defense_bonuses"]))


def load_character(database, character_id, gm):
    return database.execute(CHARACTER_SQL, (character_id, int(gm))).fetchone()


def load_progression(database, character):
    paths = load_paths(database, character)
    unlocked_rows = load_unlocked_rows(database, character["id"])
    unlocked_ranks = unlocked_rank_map(paths, unlocked_rows)
    return {"paths": paths, "unlocked_rows": unlocked_rows, "unlocked_ranks": unlocked_ranks,
            "permanent_defense_bonuses": permanent_bonuses(paths, unlocked_ranks)}


def load_paths(database, character):
    paths = []
    for specification in path_specifications(character):
        paths.extend(load_path_type(database, *specification))
    return tuple(paths)


def path_specifications(character):
    return (("class", "class_path", "class_id", character["class_id"]),
            ("racial", "racial_path", "species_id", character["species_id"]))


def load_path_type(database, path_type, table, owner_column, owner_id):
    del table, owner_column
    return paths_for_origin(database, path_type, owner_id)


def load_unlocked_rows(database, character_id):
    query = "SELECT path_type, path_id, rank FROM character_rank WHERE character_id = ?"
    return tuple(database.execute(query, (character_id,)).fetchall())


def load_action_uses(database, character_id):
    query = ("SELECT path_type, path_id, rank, uses_spent "
             "FROM character_action_use WHERE character_id = ?")
    rows = database.execute(query, (character_id,)).fetchall()
    return {(row["path_type"], row["path_id"], row["rank"]): row["uses_spent"] for row in rows}


def unlocked_rank_map(paths, rows):
    return {path_key(path): ranks_for_path(path, rows) for path in paths}


def path_key(path):
    return f"{path['path_type']}:{path['id']}"


def ranks_for_path(path, rows):
    return {row["rank"] for row in rows
            if row["path_type"] == path["path_type"] and row["path_id"] == path["id"]}


def permanent_bonuses(paths, unlocked):
    bonuses = dict.fromkeys(DEFENSES, 0)
    for path in paths:
        add_path_bonuses(bonuses, path, unlocked[path_key(path)])
    return bonuses


def add_path_bonuses(bonuses, path, unlocked):
    for rank in path["ranks"]:
        if rank["rank"] in unlocked:
            add_rank_bonuses(bonuses, rank)


def add_rank_bonuses(bonuses, rank):
    """Une clé inconnue du catalogue est ignorée plutôt que de casser toute la fiche."""
    for name, bonus in rank.get("permanent_bonuses", {}).items():
        defense_name = name.removesuffix("_defense")
        if defense_name in bonuses:
            bonuses[defense_name] += bonus


def available_racial_paths(paths, unlocked):
    return [path for path in paths
            if path["path_type"] == "racial" and 1 in unlocked[path_key(path)]]


def ability_values(character, equipped):
    accessories = accessory_bonuses(equipped)
    scores = effective_abilities(character, accessories)
    return {"accessory_ability_bonuses": accessories, "effective_scores": scores,
            "modifiers": ability_modifiers(scores)}


def accessory_bonuses(equipped):
    bonuses = dict.fromkeys(ABILITY_FIELDS, 0)
    for item in equipped:
        add_accessory_bonus(bonuses, item)
    return bonuses


def add_accessory_bonus(bonuses, item):
    field = ABILITY_ABBREVIATIONS.get(item.stat)
    if item.item_type == "accessory" and field:
        bonuses[field] += item.stat_bonus


def effective_abilities(character, accessories):
    return {field: effective_ability(character, accessories, field)
            for field in ABILITY_FIELDS}


def effective_ability(character, accessories, field):
    return (character[field] + character[f"class_{field}_bonus"]
            + character[f"racial_{field}_bonus"] + accessories[field])


def ability_modifiers(scores):
    return {field: ability_modifier(scores[field]) for field in ABILITY_FIELDS}


def defense_values(character, scores, equipped, permanent):
    return {name: defense_value(name, character, scores, equipped, permanent)
            for name in DEFENSES}


def defense_value(name, character, scores, equipped, permanent):
    _label, ability, equipment_field = DEFENSES[name]
    equipment = (getattr(item, equipment_field) for item in equipped)
    return (defense(scores[ability], equipment)
            + character[f"species_{name}_bonus"]
            + character[f"path_{name}_bonus"] + permanent[name])

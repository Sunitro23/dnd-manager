import json

from flask import render_template

from dnd_manager.characters.sheet.access import accessible_character
from dnd_manager.authentication.http import is_gm
from dnd_manager.infrastructure.database import get_db
from dnd_manager.characters.common.rules import ability_modifier
from dnd_manager.characters.sheet.actions import sheet_actions
from dnd_manager.characters.sheet.defenses import defense_context
from dnd_manager.characters.inventory.sqlite_repository import equipment_for_character

ABILITY_FIELDS = (
    "strength", "dexterity", "constitution",
    "intelligence", "wisdom", "charisma",
)
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
ACCESSORY_FIELDS = {
    "FOR": "strength", "DEX": "dexterity", "CON": "constitution",
    "INT": "intelligence", "SAG": "wisdom", "CHA": "charisma",
}


def load_character(database, character_id, gm):
    return database.execute(CHARACTER_SQL, (character_id, int(gm))).fetchone()


def load_equipment(database, character_id):
    return equipment_for_character(database, character_id)


def load_paths(database, character):
    paths = []
    for specification in path_specifications(character):
        paths.extend(load_path_type(database, *specification))
    return paths


def path_specifications(character):
    return (("class", "class_path", "class_id", character["class_id"]),
            ("racial", "racial_path", "species_id", character["species_id"]))


def load_path_type(database, path_type, table, owner_column, owner_id):
    query = f"SELECT * FROM {table} WHERE {owner_column} = ? AND configured = 1 ORDER BY name"
    rows = database.execute(query, (owner_id,)).fetchall()
    return [{**dict(row), "path_type": path_type,
             "ranks": json.loads(row["ranks_json"])} for row in rows]


def load_unlocked_rows(database, character_id):
    query = "SELECT path_type, path_id, rank FROM character_rank WHERE character_id = ?"
    return database.execute(query, (character_id,)).fetchall()


def unlocked_rank_map(paths, rows):
    return {path_key(path): ranks_for_path(path, rows) for path in paths}


def path_key(path):
    return f"{path['path_type']}:{path['id']}"


def ranks_for_path(path, rows):
    return {row["rank"] for row in rows
            if row["path_type"] == path["path_type"] and row["path_id"] == path["id"]}


def load_action_uses(database, character_id):
    query = ("SELECT path_type, path_id, rank, uses_spent "
             "FROM character_action_use WHERE character_id = ?")
    rows = database.execute(query, (character_id,)).fetchall()
    return {(row["path_type"], row["path_id"], row["rank"]): row["uses_spent"] for row in rows}


def permanent_bonuses(paths, unlocked):
    bonuses = {"physical": 0, "elemental": 0, "spiritual": 0}
    for path in paths:
        add_path_bonuses(bonuses, path, unlocked[path_key(path)])
    return bonuses


def add_path_bonuses(bonuses, path, unlocked):
    for rank in path["ranks"]:
        if rank["rank"] in unlocked:
            add_rank_bonuses(bonuses, rank)


def add_rank_bonuses(bonuses, rank):
    for name, bonus in rank.get("permanent_bonuses", {}).items():
        bonuses[name.removesuffix("_defense")] += bonus


def available_racial_paths(paths, unlocked):
    return [path for path in paths
            if path["path_type"] == "racial" and 1 in unlocked[path_key(path)]]


def accessory_bonuses(equipped):
    bonuses = {field: 0 for field in ABILITY_FIELDS}
    for item in equipped:
        add_accessory_bonus(bonuses, item)
    return bonuses


def add_accessory_bonus(bonuses, item):
    field = ACCESSORY_FIELDS.get(item.stat)
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


def render_character_sheet(character_id):
    return render_template("characters/detail.html", **sheet_context(character_id))


def sheet_context(character_id):
    context = initial_context(character_id)
    for enrich in (add_progression, add_abilities, add_actions, add_defenses):
        enrich(context)
    return context


def initial_context(character_id):
    database = get_db()
    accessible_character(character_id)
    character = load_character(database, character_id, is_gm())
    equipment = load_equipment(database, character_id)
    return {"database": database, "character": character, "equipment": equipment}


def add_progression(context):
    context.update(progression_context(context))


def progression_context(context):
    paths = load_paths(context["database"], context["character"])
    unlocked_rows = load_unlocked_rows(context["database"], context["character"]["id"])
    unlocked_ranks = unlocked_rank_map(paths, unlocked_rows)
    permanent_defense_bonuses = permanent_bonuses(paths, unlocked_ranks)
    return progression_values(paths, unlocked_rows, unlocked_ranks, permanent_defense_bonuses)


def progression_values(paths, rows, unlocked, permanent):
    return {"paths": paths, "unlocked_rows": rows, "unlocked_ranks": unlocked,
            "permanent_defense_bonuses": permanent,
            "available_racial_bonuses": available_racial_paths(paths, unlocked)}


def add_abilities(context):
    context.update(ability_context(context))


def ability_context(context):
    equipped = [item for item in context["equipment"] if item.equipped]
    accessories = accessory_bonuses(equipped)
    scores = effective_abilities(context["character"], accessories)
    return ability_values(equipped, accessories, scores)


def ability_values(equipped, accessories, scores):
    return {"equipped": equipped, "accessory_ability_bonuses": accessories,
            "effective_scores": scores, "modifiers": ability_modifiers(scores)}


def add_actions(context):
    uses = load_action_uses(context["database"], context["character"]["id"])
    actions, passives = sheet_actions(context["paths"], context["unlocked_ranks"], uses,
                                      context["modifiers"], context["equipment"],
                                      context["equipped"])
    context.update(available_actions=actions, available_passives=passives)


def add_defenses(context):
    values, breakdowns = defense_context(context["character"], context["effective_scores"],
                                         context["equipped"],
                                         context["permanent_defense_bonuses"])
    context.update(defenses=values, defense_breakdowns=breakdowns)
    context["available_path_points"] = context["character"]["level"] - len(context["unlocked_rows"])

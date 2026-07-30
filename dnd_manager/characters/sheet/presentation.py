from flask import abort, render_template

from dnd_manager.authentication.http import is_gm
from dnd_manager.characters.common.profile import load_action_uses, load_profile
from dnd_manager.characters.common.profile import available_racial_paths
from dnd_manager.characters.sheet.actions import sheet_actions
from dnd_manager.characters.sheet.defenses import defense_breakdowns
from dnd_manager.infrastructure.database import get_db


def render_character_sheet(character_id):
    return render_template("characters/detail.html", **sheet_context(character_id))


def sheet_context(character_id):
    database = get_db()
    profile = load_profile(database, character_id, is_gm())
    if profile is None:
        abort(404)
    return view_context(database, profile)


def view_context(database, profile):
    context = profile_values(profile)
    context.update(action_values(database, profile))
    return context


def profile_values(profile):
    return {
        "character": profile.character,
        "equipment": profile.equipment,
        "equipped": profile.equipped,
        "paths": profile.paths,
        "unlocked_rows": profile.unlocked_rows,
        "unlocked_ranks": profile.unlocked_ranks,
        "permanent_defense_bonuses": profile.permanent_defense_bonuses,
        "available_racial_bonuses": available_racial_paths(profile.paths,
                                                          profile.unlocked_ranks),
        "accessory_ability_bonuses": profile.accessory_ability_bonuses,
        "effective_scores": profile.effective_scores,
        "modifiers": profile.modifiers,
        "defenses": profile.defenses,
        "defense_breakdowns": defense_breakdowns(profile),
        "available_path_points": profile.character["level"] - len(profile.unlocked_rows),
    }


def action_values(database, profile):
    uses = load_action_uses(database, profile.character["id"])
    actions, passives = sheet_actions(profile.paths, profile.unlocked_ranks, uses,
                                      profile.modifiers, profile.equipment, profile.equipped)
    return {"available_actions": actions, "available_passives": passives}

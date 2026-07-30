import re

from dnd_manager.characters.common.health import adjusted_health as adjusted_health_value
from dnd_manager.characters.common.health import maximum_hp
from dnd_manager.characters.progression.contracts import (
    ActionResult,
    LevelResult,
    RacialBonusResult,
    RankResult,
)
from dnd_manager.shared.errors import InvalidRequest

def next_level(state):
    require_level_available(state.level)
    level = state.level + 1
    maximum = maximum_hp(state.hit_die, level, state.constitution + state.constitution_bonus)
    return LevelResult(state.character_id, level, adjusted_health(state, maximum), maximum)


def require_level_available(level):
    if level >= 20:
        raise InvalidRequest("Le niveau maximum est déjà atteint.")


def adjusted_health(state, maximum):
    return adjusted_health_value(state.current_hp, state.maximum_hp, maximum)


def next_rank(state, command):
    require_available_path(state.path_available)
    require_available_point(state.spent_points, state.level)
    require_incomplete_path(state.next_rank)
    return RankResult(state.character_id, command.path_type, command.path_id, state.next_rank)


def require_path_type(path_type):
    if path_type not in {"class", "racial"}:
        raise InvalidRequest("Type de voie invalide.")


def require_available_path(available):
    if not available:
        raise InvalidRequest("Cette voie n'est pas proposée à ce personnage.")


def require_available_point(spent, level):
    if spent >= level:
        raise InvalidRequest("Aucun point de voie disponible.")


def require_incomplete_path(rank):
    if rank > 5:
        raise InvalidRequest("Cette voie est déjà complète.")


def use_action(state, command):
    require_unlocked_action(state.unlocked)
    limit = state.limit if state.limit is not None else limited_uses(state.uses)
    require_limited_action(limit)
    require_remaining_use(state.spent, limit)
    return ActionResult(state.character_id, command.path_type, command.path_id,
                        command.rank, state.name, limit - state.spent - 1,
                        state.current_hp, state.maximum_hp)


def require_rank_number(rank):
    if rank not in range(1, 6):
        raise InvalidRequest("Rang invalide.")


def require_unlocked_action(unlocked):
    if not unlocked:
        raise InvalidRequest("Cette compétence n’est pas débloquée.")


def limited_uses(uses):
    match = re.match(r"^(\d+)\s+(?:fois|charges)\b", uses, re.IGNORECASE)
    return int(match.group(1)) if match else None


def require_limited_action(limit):
    if limit is None:
        raise InvalidRequest("Cette compétence n’utilise pas de compteur de repos.")


def require_remaining_use(spent, limit):
    if spent >= limit:
        raise InvalidRequest("Aucune utilisation restante.")


def apply_racial_bonus(state, command):
    require_racial_path(state.path_available)
    require_racial_rank(state.rank_unlocked)
    maximum = maximum_hp(state.hit_die, state.level,
                         state.constitution + state.constitution_bonus)
    current = adjusted_health(state, maximum)
    return RacialBonusResult(state.character_id, command.path_id, state.path_name,
                             current, maximum)


def require_racial_path(available):
    if not available:
        raise InvalidRequest("Ce bonus ne correspond pas à la race du personnage.")


def require_racial_rank(unlocked):
    if not unlocked:
        raise InvalidRequest("Débloque d’abord le rang 1 de cette voie.")

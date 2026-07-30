from dnd_manager.automation.contracts import ResolutionContext, TargetState
from dnd_manager.automation.resolver import resolve_effects
from dnd_manager.characters.progression.domain import (
    next_level,
    next_rank,
    require_path_type,
    require_rank_number,
    apply_racial_bonus,
    use_action,
)
from dnd_manager.shared.errors import ResourceNotFound


class RaiseLevel:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only):
        state = self.repository.find(character_id, public_only)
        return self.raise_found(state)

    def raise_found(self, state):
        if state is None:
            raise ResourceNotFound("Personnage introuvable.")
        result = next_level(state)
        self.repository.save_level(state, result)
        return result


class UnlockRank:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        require_path_type(command.path_type)
        state = self.repository.find_rank(character_id, public_only, command)
        return self.unlock_found(state, command)

    def unlock_found(self, state, command):
        if state is None:
            raise ResourceNotFound("Personnage introuvable.")
        result = next_rank(state, command)
        self.repository.save_rank(state, result)
        return result


class UseAction:
    def __init__(self, repository, roller=None):
        self.repository = repository
        self.roller = roller

    def execute(self, character_id, public_only, command):
        validate_action(command)
        state = self.repository.find_action(character_id, public_only, command)
        return self.use_found(state, command)

    def use_found(self, state, command):
        if state is None:
            raise ResourceNotFound("Personnage introuvable.")
        result = use_action(state, command)
        result = automate_action(state, result, self.roller)
        self.repository.save_action(state, result)
        return result


def automate_action(state, result, roller):
    if not state.effects:
        return result
    context = ResolutionContext(roller, state.ability_modifiers)
    target = TargetState(str(state.character_id), state.current_hp, state.maximum_hp)
    return automated_result(result, resolve_effects(state.effects, target, context))


def automated_result(result, resolution):
    values = vars(result) | {"current_hp": resolution.target.hit_points, "automated": True}
    return type(result)(**values)


def validate_action(command):
    require_path_type(command.path_type)
    require_rank_number(command.rank)


class ChooseRacialBonus:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, character_id, public_only, command):
        state = self.repository.find_racial_bonus(character_id, public_only, command)
        return self.choose_found(state, command)

    def choose_found(self, state, command):
        if state is None:
            raise ResourceNotFound("Personnage introuvable.")
        result = apply_racial_bonus(state, command)
        self.repository.save_racial_bonus(state, result)
        return result

from dnd_manager.automation.contracts import Dice, Formula
from dnd_manager.automation.effects import DealDamage, Heal
from dnd_manager.shared.errors import InvalidRequest


def compile_effect(specification):
    builder = BUILDERS.get(specification.get("type"))
    if builder is None:
        raise InvalidRequest("Type d’effet automatisé inconnu.")
    return builder(specification)


def compile_damage(specification):
    return DealDamage(compile_formula(specification["value"]))


def compile_heal(specification):
    return Heal(compile_formula(specification["value"]))


def compile_formula(specification):
    dice = specification["dice"]
    return Formula(Dice(dice["count"], dice["sides"]),
                   specification.get("ability_modifier"), specification.get("bonus", 0))


BUILDERS = {"deal_damage": compile_damage, "heal": compile_heal}

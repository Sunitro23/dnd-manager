from dataclasses import dataclass
from typing import Protocol

from dnd_manager.automation.contracts import (
    EffectEvent,
    Formula,
    ResolutionContext,
    TargetState,
)


class Effect(Protocol):
    def apply(self, target: TargetState, context: ResolutionContext) -> tuple[TargetState, EffectEvent]: ...


@dataclass(frozen=True)
class Heal:
    value: Formula

    def apply(self, target, context):
        amount = evaluate(self.value, context)
        updated = heal(target, amount)
        return updated, EffectEvent("heal", target.identifier, updated.hit_points - target.hit_points)


@dataclass(frozen=True)
class DealDamage:
    value: Formula

    def apply(self, target, context):
        amount = evaluate(self.value, context)
        updated = damage(target, amount)
        return updated, EffectEvent("deal_damage", target.identifier, target.hit_points - updated.hit_points)


def evaluate(formula, context):
    rolled = context.roller.roll(formula.dice.count, formula.dice.sides)
    modifier = dict(context.ability_modifiers).get(formula.modifier, 0)
    return max(0, rolled + modifier + formula.bonus)


def heal(target, amount):
    hit_points = min(target.maximum_hit_points, target.hit_points + amount)
    return TargetState(target.identifier, hit_points, target.maximum_hit_points)


def damage(target, amount):
    hit_points = max(0, target.hit_points - amount)
    return TargetState(target.identifier, hit_points, target.maximum_hit_points)

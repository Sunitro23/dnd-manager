"""Règles de jeu partagées : source unique pour le point-buy, les PV et les Défenses.

`maximum_hp` et l'ajustement des PV courants existaient en double (ici et dans un
module `health` voisin), avec des exceptions différentes. Les deux copies ont divergé et
l'une d'elles a produit une perte de PV silencieuse ; il n'en reste qu'une.
"""

import re

from dnd_manager.shared.errors import InvalidRequest

POINT_BUY_COSTS = {
    4: -4,
    5: -3,
    6: -2,
    7: -1,
    8: 0,
    9: 1,
    10: 2,
    11: 3,
    12: 4,
    13: 5,
    14: 7,
    15: 9,
    16: 11,
    17: 13,
    18: 15,
    19: 17,
    20: 19,
}

FIXED_HIT_DIE_GAINS = {6: 4, 8: 5, 10: 6, 12: 7}
POINT_BUY_BUDGET = 27
ABILITY_COUNT = 6
MINIMUM_ABILITY_SCORE = min(POINT_BUY_COSTS)
MAXIMUM_ABILITY_SCORE = max(POINT_BUY_COSTS)


def ability_rules():
    """Contrat partagé avec les formulaires : une seule table de coûts pour tout le projet."""
    return {"costs": POINT_BUY_COSTS, "budget": POINT_BUY_BUDGET,
            "minimum": MINIMUM_ABILITY_SCORE, "maximum": MAXIMUM_ABILITY_SCORE,
            "hit_die_gains": FIXED_HIT_DIE_GAINS}


def ability_modifier(score):
    return (score - 10) // 2


def point_buy_total(scores):
    try:
        return sum(POINT_BUY_COSTS[score] for score in scores)
    except KeyError as error:
        raise InvalidRequest(f"Chaque caractéristique doit être comprise entre "
                             f"{MINIMUM_ABILITY_SCORE} et {MAXIMUM_ABILITY_SCORE}.") from error


def valid_point_buy(scores):
    scores = tuple(scores)
    return len(scores) == ABILITY_COUNT and point_buy_total(scores) == POINT_BUY_BUDGET


def maximum_hp(hit_die, level, constitution):
    validate_hit_die(hit_die)
    validate_level(level)
    modifier = ability_modifier(constitution)
    return max(1, hit_die + modifier) + (level - 1) * later_hit_points(hit_die, modifier)


def validate_hit_die(hit_die):
    if hit_die not in FIXED_HIT_DIE_GAINS:
        raise InvalidRequest("Le dé de vie doit être d6, d8, d10 ou d12.")


def validate_level(level):
    if not 1 <= level <= 20:
        raise InvalidRequest("Le niveau doit être compris entre 1 et 20.")


def later_hit_points(hit_die, constitution_modifier):
    return max(1, FIXED_HIT_DIE_GAINS[hit_die] + constitution_modifier)


def adjusted_health(current, previous_maximum, maximum):
    """Un personnage à pleins PV le reste ; sinon ses PV courants sont simplement plafonnés."""
    if maximum <= 0:
        raise InvalidRequest("Les PV maximums doivent être positifs.")
    return maximum if current == previous_maximum else min(current, maximum)


def defense(score, equipped_bonuses):
    return ability_modifier(score) + sum(equipped_bonuses)


def limited_uses(uses):
    """Nombre d'utilisations avant repos décrit par un libellé (« 2 fois par Repos… »)."""
    match = re.match(r"^(\d+)\s+(?:fois|charges)\b", uses, re.IGNORECASE)
    return int(match.group(1)) if match else None

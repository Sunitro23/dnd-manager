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


def ability_modifier(score):
    return (score - 10) // 2


def point_buy_total(scores):
    try:
        return sum(POINT_BUY_COSTS[score] for score in scores)
    except KeyError as error:
        raise ValueError("Chaque caractéristique doit être comprise entre 4 et 20.") from error


def valid_point_buy(scores):
    scores = tuple(scores)
    return len(scores) == 6 and point_buy_total(scores) == 27


def maximum_hp(hit_die, level, constitution):
    validate_hit_die(hit_die)
    validate_level(level)
    modifier = ability_modifier(constitution)
    return max(1, hit_die + modifier) + (level - 1) * later_hit_points(hit_die, modifier)


def validate_hit_die(hit_die):
    if hit_die not in FIXED_HIT_DIE_GAINS:
        raise ValueError("Le dé de vie doit être d6, d8, d10 ou d12.")


def validate_level(level):
    if not 1 <= level <= 20:
        raise ValueError("Le niveau doit être compris entre 1 et 20.")


def later_hit_points(hit_die, constitution_modifier):
    return max(1, FIXED_HIT_DIE_GAINS[hit_die] + constitution_modifier)


def adjusted_current_hp(current_hp, old_max_hp, new_max_hp):
    if new_max_hp <= 0:
        raise ValueError("Les PV maximums doivent être positifs.")
    return new_max_hp if current_hp == old_max_hp else min(current_hp, new_max_hp)


def defense(score, equipped_bonuses):
    return ability_modifier(score) + sum(equipped_bonuses)

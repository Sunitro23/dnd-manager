POINT_BUY_COSTS = {
    8: 0,
    9: 1,
    10: 2,
    11: 3,
    12: 4,
    13: 5,
    14: 7,
    15: 9,
}

FIXED_HIT_DIE_GAINS = {6: 4, 8: 5, 10: 6, 12: 7}


def ability_modifier(score):
    return (score - 10) // 2


def point_buy_total(scores):
    try:
        return sum(POINT_BUY_COSTS[score] for score in scores)
    except KeyError as error:
        raise ValueError("Chaque caractéristique doit être comprise entre 8 et 15.") from error


def valid_point_buy(scores):
    scores = tuple(scores)
    return len(scores) == 6 and point_buy_total(scores) == 27


def maximum_hp(hit_die, level, constitution):
    if hit_die not in FIXED_HIT_DIE_GAINS:
        raise ValueError("Le dé de vie doit être d6, d8, d10 ou d12.")
    if not 1 <= level <= 20:
        raise ValueError("Le niveau doit être compris entre 1 et 20.")

    constitution_modifier = ability_modifier(constitution)
    first_level = max(1, hit_die + constitution_modifier)
    later_gain = max(1, FIXED_HIT_DIE_GAINS[hit_die] + constitution_modifier)
    return first_level + (level - 1) * later_gain


def adjusted_current_hp(current_hp, old_max_hp, new_max_hp):
    if new_max_hp <= 0:
        raise ValueError("Les PV maximums doivent être positifs.")
    if current_hp == old_max_hp:
        return new_max_hp
    return min(current_hp, new_max_hp)


def defense(score, equipped_bonuses):
    return ability_modifier(score) + sum(equipped_bonuses)

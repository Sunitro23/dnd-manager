from dnd_manager.shared.errors import InvalidRequest

FIXED_HIT_DIE_GAINS = {6: 4, 8: 5, 10: 6, 12: 7}


def maximum_hp(hit_die, level, constitution):
    fixed_gain = FIXED_HIT_DIE_GAINS.get(hit_die)
    if fixed_gain is None:
        raise InvalidRequest("Le dé de vie est invalide.")
    modifier = (constitution - 10) // 2
    return max(1, hit_die + modifier) + (level - 1) * max(1, fixed_gain + modifier)


def adjusted_health(current, previous_maximum, maximum):
    if current == previous_maximum:
        return maximum
    return min(current, maximum)

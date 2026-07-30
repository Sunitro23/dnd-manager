from random import SystemRandom


class RandomDiceRoller:
    def __init__(self, random=None):
        self.random = random or SystemRandom()

    def roll(self, count, sides):
        return sum(self.random.randint(1, sides) for _ in range(count))

from typing import Protocol

from dnd_manager.characters.health.contracts import HealthCommand, HealthResult, HealthState
from dnd_manager.shared.errors import InvalidRequest


class HealthOperation(Protocol):
    def calculate(self, state: HealthState, command: HealthCommand) -> int: ...


class Restore:
    def calculate(self, state, command):
        return state.maximum


class UseEstus:
    def calculate(self, state, command):
        ensure_estus_available(state)
        return state.maximum


class TakeDamage:
    def calculate(self, state, command):
        received = max(0, positive_integer(command.amount) - integer(command.defense))
        return max(0, state.current - received)


class Heal:
    def calculate(self, state, command):
        return min(state.maximum, state.current + positive_integer(command.amount))


class SetHealth:
    def calculate(self, state, command):
        return min(state.maximum, positive_integer(command.amount))


OPERATIONS: dict[str, HealthOperation] = {
    "maximum": Restore(),
    "estus": UseEstus(),
    "rest": Restore(),
    "damage": TakeDamage(),
    "heal": Heal(),
    "set": SetHealth(),
}


def calculate_health(state, command):
    operation = OPERATIONS.get(command.action)
    if operation is None:
        raise InvalidRequest("Action de PV inconnue.")
    return operation.calculate(state, command)


def health_result(state, command):
    current = calculate_health(state, command)
    return build_result(state, command, current)


def build_result(state, command, current):
    return HealthResult(state.character_id, state.current, current, state.maximum,
                        estus_status(command.action, state.estus_available),
                        command.action == "rest")


def estus_status(action, available):
    return {"estus": False, "rest": True}.get(action, available)


def ensure_estus_available(state):
    if not state.estus_available:
        raise InvalidRequest("L’Estus a déjà été utilisé depuis le dernier repos.")


def positive_integer(value):
    amount = integer(value)
    if amount < 1:
        raise InvalidRequest("Le montant doit être supérieur ou égal à 1.")
    return amount


def integer(value):
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise InvalidRequest("Le montant doit être un nombre entier.") from error

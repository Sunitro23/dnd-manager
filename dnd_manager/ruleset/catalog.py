import json
from pathlib import Path

from dnd_manager.shared.errors import RepositoryUnavailable


class JsonRulesetCatalog:
    def __init__(self, path):
        self.path = Path(path)

    def current(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RepositoryUnavailable("Le catalogue de règles est indisponible.") from error

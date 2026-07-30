import json
from functools import lru_cache
from pathlib import Path

from dnd_manager.shared.errors import RepositoryUnavailable


class JsonRulesetCatalog:
    """Le catalogue est un artefact de build immuable : le relire à chaque requête coûte
    ~500 Ko de parsing JSON. La date de modification garde le rechargement automatique."""

    def __init__(self, path):
        self.path = Path(path)

    def current(self):
        return _cached_bundle(str(self.path), self._revision_marker())

    def _revision_marker(self):
        try:
            return self.path.stat().st_mtime_ns
        except OSError as error:
            raise RepositoryUnavailable("Le catalogue de règles est indisponible.") from error


@lru_cache(maxsize=4)
def _cached_bundle(path, _modified_at):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RepositoryUnavailable("Le catalogue de règles est indisponible.") from error

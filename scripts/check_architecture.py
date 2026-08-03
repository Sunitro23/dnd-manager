"""
Vérifie les invariants d'architecture que la relecture humaine laisse passer.

Ce script était vide alors que `check.sh` l'exécutait : la CI affichait une
vérification d'architecture qui ne vérifiait rien.

Règles appliquées :
  1. Les couches pures (contracts / domain / application / ports / règles partagées)
     n'importent ni Flask ni sqlite3.
  2. Un domaine n'importe pas son adaptateur de stockage.
  3. Les adaptateurs de stockage n'importent pas Flask.
  4. Le vocabulaire partagé n'est pas redéclaré ailleurs.
  5. Aucun bloc de template neutralisé par « {% if false %} ».
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "dnd_manager"
TEMPLATES = ROOT / "templates"
PURE_MODULES = ("contracts.py", "domain.py", "application.py", "ports.py")
PURE_PACKAGES = ("dnd_manager/automation", "dnd_manager/characters/common",
                 "dnd_manager/shared")
FORBIDDEN_IN_PURE = ("flask", "sqlite3")
SHARED_VOCABULARY = ("CHARACTER_TYPES", "VISIBILITIES", "ABILITY_FIELDS",
                     "ABILITY_LABELS", "ABILITY_ABBREVIATIONS", "ITEM_TYPES",
                     "EQUIPMENT_SLOTS")
VOCABULARY_HOME = "dnd_manager/shared/catalog.py"
# `profile.py` charge un profil complet : c'est un adaptateur de lecture, pas une règle pure.
PURE_EXCEPTIONS = {"dnd_manager/characters/common/profile.py"}
DISABLED_TEMPLATE_BLOCK = "{% if false %}"


def main():
    failures = []
    for module in sorted(PACKAGE.rglob("*.py")):
        failures.extend(module_failures(module))
    failures.extend(vocabulary_failures())
    failures.extend(template_failures())
    return report(failures)


def report(failures):
    for failure in failures:
        print(f"✗ {failure}")
    if failures:
        print(f"\n{len(failures)} violation(s) d'architecture.")
        return 1
    print("Architecture : toutes les règles sont respectées.")
    return 0


def module_failures(module):
    relative = module.relative_to(ROOT).as_posix()
    imports = imported_modules(module)
    return (pure_layer_failures(relative, imports)
            + domain_failures(relative, imports)
            + repository_failures(relative, imports))


def imported_modules(module):
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def is_pure(relative):
    if relative in PURE_EXCEPTIONS:
        return False
    return (relative.endswith(PURE_MODULES)
            or any(relative.startswith(package) for package in PURE_PACKAGES))


def pure_layer_failures(relative, imports):
    if not is_pure(relative):
        return []
    return [f"{relative} : couche pure important « {name} »"
            for name in imports
            if name.split(".")[0] in FORBIDDEN_IN_PURE]


def domain_failures(relative, imports):
    if not relative.endswith(("domain.py", "contracts.py")):
        return []
    return [f"{relative} : le domaine importe son adaptateur « {name} »"
            for name in imports if "sqlite_repository" in name]


def repository_failures(relative, imports):
    if not relative.endswith("sqlite_repository.py"):
        return []
    return [f"{relative} : un adaptateur de stockage importe « {name} »"
            for name in imports if name.split(".")[0] == "flask"]


def vocabulary_failures():
    failures = []
    for module in sorted(PACKAGE.rglob("*.py")):
        relative = module.relative_to(ROOT).as_posix()
        if relative != VOCABULARY_HOME:
            failures.extend(redeclarations(relative, module))
    return failures


def redeclarations(relative, module):
    text = module.read_text(encoding="utf-8")
    return [f"{relative} : « {name} » redéclaré alors qu'il vit dans {VOCABULARY_HOME}"
            for name in SHARED_VOCABULARY
            if re.search(rf"(?m)^{name} = ", text)]


def template_failures():
    return [f"{path.relative_to(ROOT).as_posix()} : bloc neutralisé par « if false »"
            for path in sorted(TEMPLATES.rglob("*.html"))
            if DISABLED_TEMPLATE_BLOCK in path.read_text(encoding="utf-8")]


if __name__ == "__main__":
    sys.exit(main())

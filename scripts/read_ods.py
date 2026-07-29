import json
import argparse
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


NAMESPACES = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
TABLE_NAME = f"{{{NAMESPACES['table']}}}name"
ROW_REPEAT = f"{{{NAMESPACES['table']}}}number-rows-repeated"
COLUMN_REPEAT = f"{{{NAMESPACES['table']}}}number-columns-repeated"


def cell_text(cell):
    paragraphs = []
    for paragraph in cell.findall(".//text:p", NAMESPACES):
        paragraphs.append("".join(paragraph.itertext()).strip())
    return "\n".join(part for part in paragraphs if part)


def read_tables(path):
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("content.xml"))

    result = {}
    for table in root.findall(".//table:table", NAMESPACES):
        rows = []
        for row in table.findall("table:table-row", NAMESPACES):
            values = []
            for cell in row:
                if cell.tag not in {
                    f"{{{NAMESPACES['table']}}}table-cell",
                    f"{{{NAMESPACES['table']}}}covered-table-cell",
                }:
                    continue
                repeat = int(cell.get(COLUMN_REPEAT, "1"))
                values.extend([cell_text(cell)] * repeat)
            while values and not values[-1]:
                values.pop()
            if values:
                repeat = int(row.get(ROW_REPEAT, "1"))
                rows.extend([values] * min(repeat, 1000))
        result[table.get(TABLE_NAME, "")] = rows
    return result


CLASS_HIT_DICE = {
    "Chevalier": 10,
    "Roublard": 8,
    "Héraut": 8,
    "Spécialiste": 8,
    "Clerc": 8,
    "Sorcier": 6,
    "Pyromancien": 8,
}

RACE_DETAILS = {
    "Dieux": (2, 2, 0, "Les Chevaliers d’Argent seront une sous-race."),
    "Humains": (0, 0, 0, "En Carcassage : −2 Spirituelle."),
    "Démons": (
        0,
        3,
        -2,
        "Réunit les Démons, Filles du Chaos et descendants Ghru.",
    ),
    "Géants": (
        3,
        -2,
        0,
        "Extrêmement robustes, mais sensibles aux forces élémentaires.",
    ),
    "Créations de Nito": (-2, 0, 2, "Réunit les Milfanito et Fenito."),
    "Enfants de Manus": (
        0,
        -2,
        3,
        "Peuvent adopter une apparence humaine ou monstrueuse.",
    ),
    "Gyrm": (2, 0, 0, "Nains robustes et résistants."),
    "Clan du Lion": (0, 2, 2, "Résistance générale aux forces magiques."),
    "Corviens": (-2, 0, 2, "Fragiles physiquement ; leurs ailes évoluent avec eux."),
    "Murkmans": (2, -2, 0, "Amphibiens résistants, mais sensibles aux éléments."),
    "Dragons": (
        2,
        3,
        -2,
        "Leur souffle et leur capacité de vol évolueront plus tard.",
    ),
    "Hommes-Serpents": (
        2,
        0,
        -2,
        "Guerriers robustes possédant une morsure venimeuse.",
    ),
    "Hommes-champignons": (3, -2, 0, "Dépendra de la future voie choisie."),
    "Demi-Humains": (0, 0, 0, "Chimères capables d’évoluer selon leur voie."),
}

PERMANENT_RANK_BONUSES = {
    ("Dieux", "Dieu solaire", 2): {"elemental_defense": 2},
    ("Géants", "Géant Béant", 2): {
        "physical_defense": 3,
        "elemental_defense": -2,
    },
    ("Géants", "Géant d’Anor Londo", 2): {
        "physical_defense": 3,
        "spiritual_defense": -2,
    },
    ("Murkmans", "Noyé des Profondeurs", 1): {"spiritual_defense": 1},
    ("Dragons", "Dragon ancestral", 1): {
        "physical_defense": 1,
        "elemental_defense": 1,
    },
}


def grouped_paths(rows):
    groups = {}
    for owner, path, abilities, rank, activation, uses, effect in rows[3:]:
        group = groups.setdefault(owner, {})
        path_data = group.setdefault(
            path,
            {"name": path, "abilities": abilities, "ranks": []},
        )
        rank_number = int(rank)
        rank_data = {
            "rank": rank_number,
            "activation": activation,
            "uses": uses,
            "effect": effect,
        }
        permanent_bonuses = PERMANENT_RANK_BONUSES.get((owner, path, rank_number))
        if permanent_bonuses:
            rank_data["permanent_bonuses"] = permanent_bonuses
        path_data["ranks"].append(rank_data)
    return groups


def build_game_data(path):
    tables = read_tables(path)
    class_paths = grouped_paths(tables["Classes"])
    race_paths = grouped_paths(tables["Races"])
    return {
        "classes": [
            {
                "name": name,
                "hit_die": CLASS_HIT_DICE[name],
                "paths": list(paths.values()),
            }
            for name, paths in class_paths.items()
        ],
        "races": [
            {
                "name": name,
                "defenses": {
                    "physical": RACE_DETAILS[name][0],
                    "elemental": RACE_DETAILS[name][1],
                    "spiritual": RACE_DETAILS[name][2],
                },
                "particularity": RACE_DETAILS[name][3],
                "paths": list(paths.values()),
            }
            for name, paths in race_paths.items()
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--game-data", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = build_game_data(args.source) if args.game_data else read_tables(args.source)
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)

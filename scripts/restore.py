import argparse
import shutil
import sqlite3
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Restaure une sauvegarde SQLite.")
    parser.add_argument("backup", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.backup.is_file():
        raise SystemExit(f"Sauvegarde introuvable : {args.backup}")
    if args.database.exists() and not args.force:
        raise SystemExit("La base cible existe déjà. Utiliser --force après avoir arrêté le site.")

    check = sqlite3.connect(f"file:{args.backup}?mode=ro", uri=True)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        raise SystemExit(f"Sauvegarde invalide : {result}")

    args.database.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.database.with_suffix(".restore.tmp")
    shutil.copy2(args.backup, temporary)
    temporary.replace(args.database)
    print(args.database)


if __name__ == "__main__":
    main()

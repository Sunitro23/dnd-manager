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
    validate_args(args)
    validate_backup(args.backup)
    restore_backup(args.backup, args.database)
    print(args.database)


def validate_args(args):
    if not args.backup.is_file():
        raise SystemExit(f"Sauvegarde introuvable : {args.backup}")
    if args.database.exists() and not args.force:
        raise SystemExit("La base cible existe déjà. Utiliser --force après avoir arrêté le site.")


def validate_backup(backup):
    result = integrity_result(backup)
    if result != "ok":
        raise SystemExit(f"Sauvegarde invalide : {result}")


def integrity_result(backup):
    check = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    try:
        return check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()


def restore_backup(backup, database):
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_suffix(".restore.tmp")
    shutil.copy2(backup, temporary)
    temporary.replace(database)


if __name__ == "__main__":
    main()

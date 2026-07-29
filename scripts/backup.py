import argparse
import sqlite3
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Sauvegarde la campagne JDR.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--media", type=Path)
    parser.add_argument("--retention-days", type=int, default=7)
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.database.is_file():
        raise SystemExit(f"Base introuvable : {args.database}")
    if args.retention_days < 1:
        raise SystemExit("La rétention doit être d'au moins un jour.")

    args.destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    database_backup = args.destination / f"dnd-manager-{timestamp}.sqlite3"

    source_uri = f"{args.database.resolve().as_uri()}?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    destination = sqlite3.connect(database_backup)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    if args.media and args.media.is_dir():
        media_backup = args.destination / f"dnd-manager-media-{timestamp}.tar.gz"
        with tarfile.open(media_backup, "w:gz") as archive:
            archive.add(args.media, arcname="media")

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    for backup in args.destination.glob("dnd-manager-*"):
        modified = datetime.fromtimestamp(backup.stat().st_mtime, timezone.utc)
        if modified < cutoff and backup.is_file():
            backup.unlink()

    print(database_backup)


if __name__ == "__main__":
    main()

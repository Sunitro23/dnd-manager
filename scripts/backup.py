import argparse
import sqlite3
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Sauvegarde la campagne JDR.")
    add_arguments(parser)
    return parser.parse_args()


def add_arguments(parser):
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--media", type=Path)
    parser.add_argument("--retention-days", type=int, default=7)


def main():
    args = parse_args()
    print(run_backup(args))


def run_backup(args):
    validate_args(args)
    args.destination.mkdir(parents=True, exist_ok=True)
    return perform_backup(args)


def perform_backup(args):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_database(args, timestamp)
    backup_media(args, timestamp)
    prune_backups(args)
    return backup


def validate_args(args):
    if not args.database.is_file():
        raise SystemExit(f"Base introuvable : {args.database}")
    if args.retention_days < 1:
        raise SystemExit("La rétention doit être d'au moins un jour.")


def backup_database(args, timestamp):
    database_backup = args.destination / f"dnd-manager-{timestamp}.sqlite3"
    source, destination = database_connections(args.database, database_backup)
    copy_database(source, destination)
    return database_backup


def database_connections(source, destination):
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(source_uri, uri=True), sqlite3.connect(destination)


def copy_database(source, destination):
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def backup_media(args, timestamp):
    if args.media and args.media.is_dir():
        media_backup = args.destination / f"dnd-manager-media-{timestamp}.tar.gz"
        archive_media(args.media, media_backup)


def archive_media(media, destination):
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(media, arcname="media")


def prune_backups(args):
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    for backup in args.destination.glob("dnd-manager-*"):
        remove_expired_backup(backup, cutoff)


def remove_expired_backup(backup, cutoff):
    modified = datetime.fromtimestamp(backup.stat().st_mtime, timezone.utc)
    if modified < cutoff and backup.is_file():
        backup.unlink()


if __name__ == "__main__":
    main()

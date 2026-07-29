import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BackupTestCase(unittest.TestCase):
    def test_backup_and_restore_preserve_a_valid_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.sqlite3"
            backups = root / "backups"
            restored = root / "restored.sqlite3"

            database = sqlite3.connect(source)
            database.execute("CREATE TABLE example (value TEXT NOT NULL)")
            database.execute("INSERT INTO example VALUES ('campagne')")
            database.commit()
            database.close()

            backup_result = subprocess.run(
                [
                    sys.executable,
                    "scripts/backup.py",
                    "--database",
                    str(source),
                    "--destination",
                    str(backups),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            backup = Path(backup_result.stdout.strip())
            self.assertTrue(backup.is_file())

            subprocess.run(
                [
                    sys.executable,
                    "scripts/restore.py",
                    str(backup),
                    str(restored),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            database = sqlite3.connect(restored)
            try:
                integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
                value = database.execute("SELECT value FROM example").fetchone()[0]
            finally:
                database.close()

            self.assertEqual(integrity, "ok")
            self.assertEqual(value, "campagne")


if __name__ == "__main__":
    unittest.main()

"""
Maakt een back-up van de database en de geüploade bestanden in BACKUP_DIR.

Gebruik: python manage.py backup_db
Oude back-ups (ouder dan BACKUP_KEEP_DAYS) worden opgeruimd.
"""

import sqlite3
import tarfile
import time
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Back-up van de SQLite-database en de map media."

    def handle(self, *args, **options):
        backup_dir = settings.BACKUP_DIR
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # De online-back-up-API van SQLite maakt een consistente kopie, ook terwijl de site draait.
        db_target = backup_dir / f"db-{stamp}.sqlite3"
        source = sqlite3.connect(connection.settings_dict["NAME"])
        target = sqlite3.connect(db_target)
        with target:
            source.backup(target)
        source.close()
        target.close()

        media_target = backup_dir / f"media-{stamp}.tar.gz"
        if settings.MEDIA_ROOT.exists():
            with tarfile.open(media_target, "w:gz") as archive:
                archive.add(settings.MEDIA_ROOT, arcname="media")

        cutoff = time.time() - settings.BACKUP_KEEP_DAYS * 86400
        for old in backup_dir.glob("*-*"):
            if old.stat().st_mtime < cutoff:
                old.unlink()

        self.stdout.write(self.style.SUCCESS(f"Back-up gemaakt: {db_target.name}"))

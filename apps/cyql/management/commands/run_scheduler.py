"""
Draait op de achtergrond in de container en start de Cyql-sync op het uur
uit Instellingen > Integraties. Wijzig je dat uur, dan geldt het meteen.
"""

import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.cyql.scheduler import sync_due
from apps.cyql.sync import run_sync

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Planner voor de nachtelijke Cyql-synchronisatie."

    def handle(self, *args, **options):
        if not settings.CYQL_API_KEY:
            logger.warning("CYQL_API_KEY ontbreekt: geen Cyql-synchronisatie.")
        while True:
            close_old_connections()
            try:
                if settings.CYQL_API_KEY and sync_due():
                    run = run_sync()
                    logger.info("Cyql-sync %s: %s", "gelukt" if run.ok else "mislukt", run.message.replace("\n", "; "))
            except Exception:
                logger.exception("Planner: fout bij de Cyql-sync")
            time.sleep(60)

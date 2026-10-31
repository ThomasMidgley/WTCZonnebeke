"""Haalt de gegevens van de club op uit Cyql en bewaart ze in de database.

De website leest altijd uit de eigen database, nooit rechtstreeks uit Cyql:
zo blijft de site snel en verbruikt een bezoeker geen API-budget.
"""

import logging

from django.utils import timezone

from .client import CyqlClient, CyqlError
from .models import ClubStats, SyncRun

logger = logging.getLogger(__name__)

CLUB_STATS_QUERY = "{ clubStats { memberCount } }"


def sync_club_stats(client):
    data = client.query(CLUB_STATS_QUERY)
    stats = ClubStats.load()
    stats.member_count = (data.get("clubStats") or {}).get("memberCount")
    stats.save()
    return f"{stats.member_count} leden"


STEPS = [("clubcijfers", sync_club_stats)]


def run_sync(client=None):
    client = client or CyqlClient()
    run = SyncRun.objects.create()
    lines, ok = [], True
    for label, step in STEPS:
        try:
            lines.append(f"{label}: {step(client)}")
        except CyqlError as exc:
            ok = False
            lines.append(f"{label}: mislukt ({exc.code}: {exc})")
            logger.warning("Cyql-sync %s mislukt: %s %s", label, exc.code, exc)
            if exc.code in ("NoApiKey", "ApiKeyInvalid", "ExceedingApiKeyLimit", "ExceedingComplexityBudget"):
                break
    run.ok = ok
    run.message = "\n".join(lines)
    run.remaining_budget = client.remaining
    run.finished_at = timezone.now()
    run.save()
    return run

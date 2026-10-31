"""Haalt de gegevens van de club op uit Cyql en bewaart ze in de database.

De website leest altijd uit de eigen database, nooit rechtstreeks uit Cyql:
zo blijft de site snel en verbruikt een bezoeker geen API-budget.

Budget (oktober 2026): 200 per vraag, 5.000 per week voor de hele club.
Kosten volgens Cyql: 1 per veld, +1 per veld met subvelden, en de velden onder
`items` tellen maal ceil(pageSize / 10). Eén nachtelijke sync kost zo ongeveer
300 punten; het werkelijke verbruik staat in het verslag.
"""

import logging

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .client import CyqlClient, CyqlError
from .models import Challenge, ChallengeScore, ClubEvent, ClubStats, Member, Ride, SyncRun

logger = logging.getLogger(__name__)

# Bovengrens per stap, zodat een fout of een grote club het weekbudget niet kan opsouperen.
MAX_PAGES = 5

CLUB_STATS_QUERY = "{ clubStats { memberCount } }"
RIDES_QUERY = """query($page: Int) { rides(isUpcoming: true, page: $page, pageSize: 20) {
  items { id title startTime location distance averageSpeed rideType shareUrl gpxUrl labels { title } }
  hasNextPage } }"""
EVENTS_QUERY = """query($page: Int) { events(fetchType: UPCOMING, page: $page, pageSize: 10) {
  items { id title startDateTime endTime location } hasNextPage } }"""
CHALLENGES_QUERY = """query($page: Int) { challenges(page: $page, pageSize: 10) {
  items { id title scoreType startDate endDate participantCount } hasNextPage } }"""
SCORES_QUERY = """query($id: UUID, $page: Int) { challengeScores(challengeId: $id, page: $page, pageSize: 100) {
  items { memberName score rank rideCount } hasNextPage } }"""
MEMBERS_QUERY = """query($page: Int) { members(memberStatus: APPROVED, page: $page, pageSize: 100) {
  items { id firstName lastName email status } hasNextPage } }"""


def fetch_all(client, query, field, variables=None):
    """Alle pagina's van een gepagineerde vraag, met MAX_PAGES als vangnet."""
    items = []
    for page in range(1, MAX_PAGES + 1):
        result = client.query(query, {**(variables or {}), "page": page}).get(field)
        if not result:
            break
        items.extend(result.get("items") or [])
        if not result.get("hasNextPage"):
            break
    return items


def dt(value):
    return parse_datetime(value) if value else None


def sync_club_stats(client):
    data = client.query(CLUB_STATS_QUERY)
    stats = ClubStats.load()
    stats.member_count = (data.get("clubStats") or {}).get("memberCount")
    stats.save()
    return f"{stats.member_count} leden"


def sync_rides(client):
    items = fetch_all(client, RIDES_QUERY, "rides")
    with transaction.atomic():
        Ride.objects.all().delete()
        Ride.objects.bulk_create(
            Ride(
                cyql_id=item["id"],
                title=(item.get("title") or "Clubrit")[:255],
                start_time=dt(item["startTime"]),
                location=(item.get("location") or "")[:255],
                distance=item.get("distance"),
                average_speed=item.get("averageSpeed"),
                ride_type=item.get("rideType") or "",
                labels=", ".join(label["title"] for label in item.get("labels") or [] if label.get("title"))[:255],
                share_url=item.get("shareUrl") or "",
                gpx_url=item.get("gpxUrl") or "",
            )
            for item in items
            if item.get("startTime")
        )
    return f"{len(items)} komende ritten"


def sync_events(client):
    items = fetch_all(client, EVENTS_QUERY, "events")
    with transaction.atomic():
        ClubEvent.objects.all().delete()
        ClubEvent.objects.bulk_create(
            ClubEvent(
                cyql_id=item["id"],
                title=(item.get("title") or "Activiteit")[:255],
                start_time=dt(item["startDateTime"]),
                end_time=dt(item.get("endTime")),
                location=(item.get("location") or "")[:255],
            )
            for item in items
            if item.get("startDateTime")
        )
    return f"{len(items)} komende activiteiten"


def sync_challenges(client):
    items = fetch_all(client, CHALLENGES_QUERY, "challenges")
    seen = []
    with transaction.atomic():
        for item in items:
            # Bestaande klassementen behouden de keuze "tonen" en de volgorde van de beheerder.
            Challenge.objects.update_or_create(
                cyql_id=item["id"],
                defaults={
                    "title": (item.get("title") or "Klassement")[:255],
                    "score_type": item.get("scoreType") or "",
                    "start_date": dt(item.get("startDate")),
                    "end_date": dt(item.get("endDate")),
                    "participant_count": item.get("participantCount"),
                    "is_active": True,
                },
            )
            seen.append(item["id"])
        Challenge.objects.exclude(cyql_id__in=seen).update(is_active=False)

    lines = [f"{len(items)} klassementen"]
    for challenge in Challenge.objects.filter(is_active=True, show_on_site=True):
        scores = fetch_all(client, SCORES_QUERY, "challengeScores", {"id": str(challenge.cyql_id)})
        with transaction.atomic():
            challenge.scores.all().delete()
            ChallengeScore.objects.bulk_create(
                ChallengeScore(
                    challenge=challenge,
                    rank=score.get("rank") or 0,
                    member_name=(score.get("memberName") or "")[:255],
                    score=score.get("score") or 0,
                    ride_count=score.get("rideCount"),
                )
                for score in scores
            )
            challenge.scores_updated_at = timezone.now()
            challenge.save(update_fields=["scores_updated_at"])
        lines.append(f"{challenge.title}: {len(scores)} deelnemers")
    return ", ".join(lines)


def sync_members(client):
    items = fetch_all(client, MEMBERS_QUERY, "members")
    with transaction.atomic():
        Member.objects.all().delete()
        Member.objects.bulk_create(
            Member(
                cyql_id=item["id"],
                first_name=(item.get("firstName") or "")[:120],
                last_name=(item.get("lastName") or "")[:120],
                email=(item.get("email") or "").strip().lower()[:254],
                status=item.get("status") or "",
            )
            for item in items
        )
    return f"{len(items)} goedgekeurde leden"


STEPS = [
    ("clubcijfers", sync_club_stats),
    ("kalender", sync_rides),
    ("activiteiten", sync_events),
    ("klassement", sync_challenges),
    ("leden", sync_members),
]

# Na deze fouten heeft verder proberen geen zin (en kost het enkel budget).
FATAL = ("NoApiKey", "ApiKeyInvalid", "ExceedingApiKeyLimit", "ExceedingComplexityBudget")


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
            if exc.code in FATAL:
                break
    run.ok = ok
    run.message = "\n".join(lines)
    run.remaining_budget = client.remaining
    run.finished_at = timezone.now()
    run.save()
    return run

import datetime

from django.utils import timezone

from apps.core.models import CyqlApp

from .models import SyncRun


def sync_due(now=None):
    """Is de nachtelijke sync van vandaag aan de beurt? Het uur staat bij Cyql > Instellingen."""
    now = timezone.localtime(now)
    sync_time = CyqlApp.load().sync_time
    due_at = timezone.make_aware(datetime.datetime.combine(now.date(), sync_time))
    if now < due_at:
        return False
    return not SyncRun.objects.filter(started_at__gte=due_at).exists()

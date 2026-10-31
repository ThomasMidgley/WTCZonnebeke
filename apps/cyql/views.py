import logging

import requests
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.text import slugify

from .models import Ride, SyncRun
from .sync import run_sync


def sync_now(request):
    """Synchroniseert meteen, bv. na een wijziging in Cyql. Kost API-budget, dus enkel voor beheerders."""
    if not request.user.is_superuser:
        raise PermissionDenied
    if request.method == "POST":
        run = run_sync()
        if run.ok:
            messages.success(request, "Cyql is gesynchroniseerd.")
        else:
            messages.error(request, "De synchronisatie is (deels) mislukt. Bekijk het verslag.")
        return redirect("cyql_sync:index")
    return TemplateResponse(request, "cyql/sync_now.html", {"last_run": SyncRun.objects.first()})


logger = logging.getLogger(__name__)
GPX_MAX_BYTES = 10 * 1024 * 1024


def ride_gpx(request, ride_id):
    """Geeft de GPX van een rit als download.

    Cyql serveert het bestand als XML, waardoor browsers het tonen in plaats van
    het op te slaan. Daarom halen we het hier op en sturen we het door als
    bijlage. Enkel adressen die Cyql zelf bij een rit meegaf, worden opgehaald.
    """
    ride = get_object_or_404(Ride, cyql_id=ride_id)
    if not ride.gpx_url.startswith("https://"):
        raise Http404
    try:
        response = requests.get(ride.gpx_url, timeout=15, stream=True)
        response.raise_for_status()
        content = response.raw.read(GPX_MAX_BYTES + 1, decode_content=True)
    except requests.RequestException as exc:
        logger.warning("GPX van rit %s niet op te halen: %s", ride.cyql_id, exc.__class__.__name__)
        raise Http404 from exc
    if len(content) > GPX_MAX_BYTES:
        raise Http404
    day = timezone.localtime(ride.start_time).strftime("%Y-%m-%d")
    filename = f"{day}-{slugify(ride.title) or 'rit'}.gpx"
    result = HttpResponse(content, content_type="application/gpx+xml")
    result["Content-Disposition"] = f'attachment; filename="{filename}"'
    result["Cache-Control"] = "public, max-age=3600"
    return result

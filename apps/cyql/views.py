from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from .models import SyncRun
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

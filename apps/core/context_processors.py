from django.conf import settings

from .models import Sponsor


def site_context(request):
    if request.path.startswith("/admin/"):
        return {}
    return {
        "site_noindex": settings.SITE_NOINDEX,
        "main_sponsors": Sponsor.objects.filter(is_visible=True, is_main=True).select_related("logo"),
    }

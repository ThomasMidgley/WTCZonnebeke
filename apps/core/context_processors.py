from django.conf import settings

from .models import Sponsor


def site_context(request):
    if request.path.startswith("/admin/"):
        return {}
    # Enkel lezen: zo krijgt een bezoeker zonder mandje geen sessiecookie.
    cart = request.session.get("winkelmandje", []) if hasattr(request, "session") else []
    return {
        "cart_count": sum(item.get("qty", 0) for item in cart),
        "site_noindex": settings.SITE_NOINDEX,
        "main_sponsors": Sponsor.objects.filter(is_visible=True, is_main=True).select_related("logo"),
    }

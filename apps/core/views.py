from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

from .models import Huisstijl, QrInfo


def legacy_index(request):
    """De QR-codes op de pijltjes wijzen naar /index.php?id=900. Andere id's gaan naar de home."""
    if request.GET.get("id") == "900":
        return render(request, "core/qr_info.html", {"info": QrInfo.load(request_or_site=request)})
    if request.GET.get("id"):
        raise Http404
    return redirect("/", permanent=True)


@cache_control(max_age=3600, public=True)
def robots_txt(request):
    if settings.SITE_NOINDEX:
        body = "User-agent: *\nDisallow: /\n"
    else:
        body = "User-agent: *\nDisallow: /admin/\nDisallow: /formulier/\n"
    return HttpResponse(body, content_type="text/plain")


@cache_control(max_age=86400, public=True)
def manifest(request):
    huisstijl = Huisstijl.load(request_or_site=request)
    return JsonResponse(
        {
            "name": "WTC Zonnebeke",
            "short_name": "WTC Zonnebeke",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#FFFFFF",
            "theme_color": huisstijl.primary_color,
            "icons": [
                {"src": static("img/icon.svg"), "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
                {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            ],
        },
        content_type="application/manifest+json",
    )


def health(request):
    return HttpResponse("ok", content_type="text/plain")

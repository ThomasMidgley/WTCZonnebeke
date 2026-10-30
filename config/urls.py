from django.conf import settings
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from apps.accounts import views as account_views
from apps.core import views as core_views

urlpatterns = [
    # Aanmelden via Microsoft 365 vervangt het standaard aanmeldscherm.
    path("admin/login/", account_views.login_view, name="wagtailadmin_login"),
    path("admin/login/callback/", account_views.callback_view, name="sso_callback"),
    path("accounts/", include("apps.accounts.urls")),
    path("admin/", include(wagtailadmin_urls)),
    path("documenten/", include(wagtaildocs_urls)),
    # QR-codes op de pijltjes verwijzen naar deze oude URL: nooit wijzigen.
    path("index.php", core_views.legacy_index, name="legacy_index"),
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    path("manifest.webmanifest", core_views.manifest, name="manifest"),
    path("gezond/", core_views.health, name="health"),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    from django.views.static import serve

    # Geüploade foto's en documenten; Cloudflare cachet ze.
    urlpatterns += [path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT})]

urlpatterns += [path("", include(wagtail_urls))]

from django.conf import settings
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from apps.accounts import views as account_views
from apps.core import views as core_views
from apps.cyql import views as cyql_views
from apps.formulieren import views as formulier_views
from apps.shop import views as shop_views

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
    path("gpx/<uuid:ride_id>/", cyql_views.ride_gpx, name="ride_gpx"),
    path("winkelmandje/", shop_views.cart_view, name="shop_cart"),
    path("afrekenen/", shop_views.checkout_view, name="shop_checkout"),
    path("bestelling/<str:token>/", shop_views.order_view, name="shop_order"),
    path("stripe/webhook/", shop_views.stripe_webhook, name="stripe_webhook"),
    path("stock/", include("apps.shop.stock_urls")),
    path("formulier/<slug:code>/", formulier_views.form_view, name="formulier"),
    path("formulier/<slug:code>/bedankt/", formulier_views.form_done, name="formulier_klaar"),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    from django.views.static import serve

    # Geüploade foto's en documenten; Cloudflare cachet ze.
    urlpatterns += [path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT})]

urlpatterns += [path("", include(wagtail_urls))]

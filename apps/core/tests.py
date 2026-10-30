from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.roles import STOCK_GROUP
from apps.core import colors
from apps.core.models import Huisstijl, Integraties, QrInfo, Toegang

TENANT = "00000000-0000-0000-0000-000000000001"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)

    def test_all_pages_render(self):
        for url in [
            "/", "/lid-worden/", "/evenementen/", "/evenementen/wacaca/", "/evenementen/nonnebossentocht/",
            "/kalender/", "/klassement/", "/bestuur/", "/clubreglement/", "/cyql/", "/contact/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_home_shows_main_sponsors_and_footer(self):
        html = self.client.get("/").content.decode()
        for name in ["Fietstechniek Gheysen", "De Oude Timmerie", "Garage Ghesquiere", "Deneut Sanitair"]:
            self.assertIn(name, html)
        self.assertIn('href="https://www.postmill.be"', html)
        self.assertIn("© WTC Zonnebeke vzw", html)

    def test_qr_page_keeps_old_address(self):
        response = self.client.get("/index.php?id=900")
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("EVENEMENTEN QR INFO", html)
        self.assertIn("0478 27 67 85", html)
        self.assertIn("Zaterdag 11 april 2026", html)
        self.assertNotIn("site-header", html)

    def test_qr_page_date_follows_settings(self):
        info = QrInfo.load()
        info.event_date = "2027-04-10"
        info.save()
        self.assertIn("Zaterdag 10 april 2027", self.client.get("/index.php?id=900").content.decode())

    def test_legacy_urls_redirect(self):
        self.assertRedirects(self.client.get("/pagina/170"), "/bestuur/", status_code=301)
        self.assertRedirects(
            self.client.get("/%5Cpagina/160"), "/pagina/160", status_code=301, fetch_redirect_response=False
        )
        self.assertRedirects(self.client.get("/index.php"), "/", status_code=301)
        self.assertEqual(self.client.get("/index.php?id=12").status_code, 404)

    def test_robots_blocks_test_environment(self):
        self.assertIn("Disallow: /", self.client.get("/robots.txt").content.decode())

    def test_no_third_party_requests_on_event_page(self):
        html = self.client.get("/evenementen/nonnebossentocht/").content.decode()
        self.assertIn('data-youtube="rI-Dcwxhtbo"', html)
        self.assertNotIn("<iframe", html)

    def test_contact_form_sends_mail_with_reply_to(self):
        response = self.client.post(
            "/contact/",
            {"naam": "Jan", "e_mailadres": "jan@example.com", "gsm_nummer": "", "bericht": "Mag ik meerijden?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].reply_to, ["jan@example.com"])
        self.assertIn("Mag ik meerijden?", mail.outbox[0].body)

    def test_contact_honeypot_drops_spam(self):
        self.client.post(
            "/contact/",
            {"naam": "Bot", "e_mailadres": "bot@example.com", "bericht": "spam", "website": "http://spam"},
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_theme_colors_are_injected(self):
        huisstijl = Huisstijl.load()
        huisstijl.primary_color = "#003366"
        huisstijl.save()
        self.assertIn("--primary:#003366", self.client.get("/").content.decode())

    def test_admin_requires_login(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class ColorTests(TestCase):
    def test_contrast(self):
        self.assertAlmostEqual(colors.contrast("#FFFFFF", "#000000"), 21, places=0)
        self.assertGreater(colors.contrast(colors.darken_until("#FF5200"), "#FFFFFF"), 4.5)

    def test_light_primary_is_rejected(self):
        with self.assertRaises(ValidationError):
            Huisstijl(primary_color="#FFEE00", accent_color="#FF5200").clean()
        Huisstijl(primary_color="#231F20", accent_color="#FF5200").clean()


def fake_msal(claims):
    app = mock.Mock()
    app.initiate_auth_code_flow.return_value = {"auth_uri": "https://login.microsoftonline.com/x", "state": "s"}
    app.acquire_token_by_auth_code_flow.return_value = {"id_token_claims": claims}
    return mock.patch("apps.accounts.views.msal.ConfidentialClientApplication", return_value=app)


@override_settings(AZURE_CLIENT_SECRET="test-secret", BOOTSTRAP_ADMIN_EMAILS=[])
class SsoTests(TestCase):
    def setUp(self):
        integraties = Integraties.load()
        integraties.azure_tenant_id = TENANT
        integraties.azure_client_id = "client-id"
        integraties.save()
        toegang = Toegang.load()
        toegang.admin_emails = "beheer@example.be"
        toegang.stock_emails = "Stock@example.be"
        toegang.save()

    def sign_in(self, email, tenant=TENANT):
        claims = {"tid": tenant, "preferred_username": email, "given_name": "Test", "family_name": "Lid"}
        with fake_msal(claims):
            start = self.client.get("/admin/login/?start=1&next=/admin/pages/")
            self.assertEqual(start.status_code, 302)
            return self.client.get("/admin/login/callback/?code=abc&state=s")

    def test_admin_gets_full_access(self):
        response = self.sign_in("beheer@example.be")
        self.assertRedirects(response, "/admin/pages/", fetch_redirect_response=False)
        user = get_user_model().objects.get(username="beheer@example.be")
        self.assertTrue(user.is_superuser)

    def test_stock_manager_gets_limited_access(self):
        self.sign_in("stock@example.be")
        user = get_user_model().objects.get(username="stock@example.be")
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.groups.filter(name=STOCK_GROUP).exists())
        self.assertTrue(user.has_perm("wagtailadmin.access_admin"))

    def test_unknown_user_is_denied(self):
        response = self.sign_in("iemand@example.be")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="iemand@example.be").exists())

    def test_other_tenant_is_denied(self):
        response = self.sign_in("beheer@example.be", tenant="other")
        self.assertEqual(response.status_code, 403)

    def test_removed_admin_loses_access(self):
        self.sign_in("beheer@example.be")
        self.client.logout()
        toegang = Toegang.load()
        toegang.admin_emails = ""
        toegang.save()
        self.assertEqual(self.sign_in("beheer@example.be").status_code, 403)
        self.assertFalse(get_user_model().objects.get(username="beheer@example.be").is_staff)

    def test_open_redirect_is_blocked(self):
        claims = {"tid": TENANT, "preferred_username": "beheer@example.be"}
        with fake_msal(claims):
            self.client.get("/admin/login/?start=1&next=https://evil.example/")
            response = self.client.get("/admin/login/callback/?code=abc&state=s")
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)

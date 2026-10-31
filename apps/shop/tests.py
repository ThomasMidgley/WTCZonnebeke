import hashlib
import hmac
import json
import time
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.template import Context, Template
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.roles import stock_group
from apps.core.models import CyqlApp, Toegang
from apps.cyql.models import Member

from . import services
from .models import Order, Product, StockMovement, Variant


def fake_session(id="cs_test_1"):
    return id, "https://checkout.stripe.com/c/pay/cs_test_1"


@override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET="whsec_x")
class ShopBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        cls.trui = Product.objects.get(slug="trui-korte-mouw")
        cls.pakket = Product.objects.get(slug="clubpakket")
        cls.trui_m = cls.trui.variants.get(gender="H", size="M")
        cls.trui_xs = cls.trui.variants.get(gender="H", size="XS")
        Member.objects.create(cyql_id="11111111-1111-1111-1111-111111111111", first_name="Jan", last_name="Peeters",
                              email="jan@example.com", status="APPROVED")
        toegang = Toegang.load()
        toegang.stock_emails = "kledij@example.com"
        toegang.save()

    def add_to_cart(self, product, variants, qty=1):
        data = {f"variant_{i}": str(v.pk) for i, v in enumerate(variants)}
        data["qty"] = str(qty)
        return self.client.post(f"/shop/{product.slug}/", data)

    def checkout(self, email="jan@example.com"):
        data = {"name": "Jan Peeters", "email": email, "phone": "0470 12 34 56", "note": "", "accept": "on"}
        with mock.patch("apps.shop.payments.create_checkout_session", return_value=fake_session()):
            return self.client.post("/afrekenen/", data)

    def webhook(self, event_type, session_id="cs_test_1", payment_status="paid"):
        # Echt ondertekend bericht, zoals Stripe het stuurt: zo test je ook de handtekening en het formaat.
        payload = json.dumps({"id": "evt_1", "object": "event", "type": event_type, "data": {"object": {
            "id": session_id, "object": "checkout.session", "payment_status": payment_status,
            "payment_intent": "pi_1"}}})
        timestamp = int(time.time())
        signature = hmac.new(b"whsec_x", f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()
        return self.client.post("/stripe/webhook/", payload, content_type="application/json",
                                HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}")



class ShopTests(ShopBase):
    # ------------------------------------------------------------ startinhoud

    def test_seed_from_stock_list(self):
        self.assertEqual(Product.objects.filter(kind=Product.KIND_ARTICLE).count(), 10)
        self.assertEqual(self.pakket.price, Decimal("180"))
        self.assertEqual(
            [c.component.slug for c in self.pakket.components.all()],
            ["trui-korte-mouw", "trui-lange-mouw", "korte-broek-bretellen", "lange-broek", "body", "kousen"],
        )
        self.assertEqual(self.trui_m.article_number, "41361")
        self.assertEqual(self.trui.variants.get(gender="D", size="M").article_number, "41361 D")
        call_command("seed_site", verbosity=0)
        self.assertEqual(Product.objects.count(), 14)  # 10 artikels, pakket, 3 soorten lidgeld

    def test_shop_pages(self):
        response = self.client.get("/shop/")
        self.assertContains(response, "Clubpakket")
        self.assertContains(response, "41")
        response = self.client.get("/shop/clubpakket/")
        self.assertContains(response, "Kousen")
        self.assertContains(response, "(voorbestelling)")
        self.assertNotIn("sessionid", response.cookies)

    # ------------------------------------------------------------ mandje en bestelling

    def test_cart_and_checkout(self):
        response = self.add_to_cart(self.trui, [self.trui_m], 2)
        self.assertRedirects(response, "/winkelmandje/")
        self.assertContains(self.client.get("/winkelmandje/"), "Trui korte mouw")
        response = self.checkout()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://checkout.stripe.com/"))
        order = Order.objects.get()
        self.assertEqual(order.status, Order.PENDING)
        self.assertEqual(order.total, Decimal("82"))
        self.assertEqual(order.stripe_session_id, "cs_test_1")
        # 30 minuten vastgehouden
        self.assertEqual(self.trui_m.reserved, 2)
        self.assertEqual(self.trui_m.available, 1)
        self.assertEqual(self.client.session.get("winkelmandje"), [])

    def test_package_price_on_first_part(self):
        parts = [c.component.variants.filter(size="M").first() for c in self.pakket.components.all()]
        self.add_to_cart(self.pakket, parts)
        self.checkout()
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("180"))
        self.assertEqual(order.lines.count(), 6)
        self.assertEqual(sum(line.line_total for line in order.lines.all()), Decimal("180"))
        self.assertTrue(all(line.package_id == self.pakket.pk for line in order.lines.all()))

    def test_members_only(self):
        self.add_to_cart(self.trui, [self.trui_m])
        response = self.checkout(email="vreemde@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "enkel voor leden")
        self.assertFalse(Order.objects.exists())

    def test_preorder_when_out_of_stock(self):
        self.add_to_cart(self.trui, [self.trui_xs])
        self.assertContains(self.client.get("/afrekenen/"), "niet op voorraad")
        self.checkout()
        self.assertTrue(Order.objects.get().has_preorder)

    # ------------------------------------------------------------ Stripe

    def test_webhook_paid_sends_mails_once(self):
        self.add_to_cart(self.trui, [self.trui_m])
        self.checkout()
        self.webhook("checkout.session.completed")
        self.webhook("checkout.session.completed")
        order = Order.objects.get()
        self.assertEqual(order.status, Order.PAID)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["jan@example.com"])
        self.assertIn(order.number, mail.outbox[0].subject)
        self.assertEqual(mail.outbox[1].to, ["kledij@example.com"])

    def test_webhook_bancontact_pending_then_paid(self):
        self.add_to_cart(self.trui, [self.trui_m])
        self.checkout()
        self.webhook("checkout.session.completed", payment_status="unpaid")
        self.assertEqual(Order.objects.get().status, Order.PENDING)
        self.webhook("checkout.session.async_payment_succeeded")
        self.assertEqual(Order.objects.get().status, Order.PAID)

    def test_webhook_failed_and_expired_release_stock(self):
        self.add_to_cart(self.trui, [self.trui_m])
        self.checkout()
        self.webhook("checkout.session.expired")
        self.assertEqual(Order.objects.get().status, Order.EXPIRED)
        self.assertEqual(self.trui_m.reserved, 0)

    def test_webhook_bad_signature(self):
        response = self.client.post("/stripe/webhook/", b"{}", content_type="application/json",
                                    HTTP_STRIPE_SIGNATURE="t=1,v1=fout")
        self.assertEqual(response.status_code, 400)

    def test_expire_pending(self):
        self.add_to_cart(self.trui, [self.trui_m])
        self.checkout()
        self.assertEqual(services.expire_pending(timezone.now() + timedelta(minutes=31)), 1)
        self.assertEqual(Order.objects.get().status, Order.EXPIRED)

    # ------------------------------------------------------------ stockbeheer

    def paid_order(self):
        self.add_to_cart(self.trui, [self.trui_m])
        self.checkout()
        self.webhook("checkout.session.completed")
        return Order.objects.get()

    def stock_user(self):
        user = get_user_model().objects.create_user("xavier", email="xavier@example.com", is_staff=True)
        user.groups.add(stock_group())
        return user

    def test_stock_app_access(self):
        response = self.client.get("/stock/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        other = get_user_model().objects.create_user("lid", email="lid@example.com")
        self.client.force_login(other)
        self.assertEqual(self.client.get("/stock/").status_code, 403)
        self.client.force_login(self.stock_user())
        for url in ("/stock/", "/stock/voorraad/", "/stock/zoeken/?q=Jan", "/stock/logboek/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_ready_and_delivered(self):
        order = self.paid_order()
        user = self.stock_user()
        self.client.force_login(user)
        self.assertContains(self.client.get("/stock/"), order.number)
        mail.outbox.clear()
        self.client.post(f"/stock/bestelling/{order.pk}/klaar/")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.READY)
        self.assertIn("klaar", mail.outbox[0].subject)
        self.client.post(f"/stock/bestelling/{order.pk}/geleverd/")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.DELIVERED)
        self.trui_m.refresh_from_db()
        self.assertEqual(self.trui_m.stock, 2)
        self.assertEqual(self.trui_m.reserved, 0)
        movement = StockMovement.objects.get()
        self.assertEqual((movement.delta, movement.user), (-1, user))

    def test_not_collected_after_four_weeks(self):
        order = self.paid_order()
        services.mark_ready(order, None)
        self.assertFalse(services.mark_not_collected(order, None))
        Order.objects.filter(pk=order.pk).update(ready_at=timezone.now() - timedelta(weeks=4, days=1))
        order.refresh_from_db()
        self.assertTrue(services.mark_not_collected(order, None))
        self.assertEqual(self.trui_m.reserved, 0)

    def test_adjust_needs_reason(self):
        self.client.force_login(self.stock_user())
        url = f"/stock/voorraad/{self.trui_m.pk}/"
        response = self.client.post(url, {"delta": "5", "reason": ""})
        self.assertEqual(response.status_code, 200)
        self.client.post(url, {"delta": "5", "reason": "Levering Bioracer", "detail": ""})
        self.assertEqual(Variant.objects.get(pk=self.trui_m.pk).stock, 8)
        self.assertEqual(StockMovement.objects.get().reason, "Levering Bioracer")

    def test_admin_menu_for_stock_user(self):
        self.client.force_login(self.stock_user())
        self.assertEqual(self.client.get("/admin/shop_orders/").status_code, 200)
        self.assertEqual(self.client.get("/admin/shop_products/").status_code, 302)


class EuroFilterTests(TestCase):
    def test_euro(self):
        template = Template("{% load wtc %}{{ a|euro }} {{ b|euro }}")
        self.assertEqual(template.render(Context({"a": Decimal("180.00"), "b": Decimal("1234.5")})), "180 1.234,50")


class CspTests(TestCase):
    def test_checkout_may_redirect_to_stripe(self):
        # Zonder dit blokkeert de browser de doorverwijzing na het betaalformulier.
        csp = self.client.get("/winkelmandje/")["Content-Security-Policy"]
        self.assertIn("form-action 'self' https://checkout.stripe.com", csp)


@override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET="whsec_x")
class EventTests(ShopBase):
    """Events en inschrijvingen: geen maten, wel plaatsen, prijs volgens datum en extra vragen."""

    def setUp(self):
        self.feest = Product.objects.create(
            slug="clubfeest", title="Clubfeest", kind=Product.KIND_EVENT, price=Decimal("70"), max_places=3,
            members_only=False,
        )
        self.lidgeld = Product.objects.get(slug="lidgeld")
        cyql = CyqlApp.load()
        cyql.invite_link = "https://cyql.example/uitnodiging"
        cyql.save()

    def test_shop_has_four_categories(self):
        response = self.client.get("/shop/")
        for heading in ("Artikels", "Pakketten", "Events", "Lidgeld"):
            self.assertContains(response, f">{heading}</h2>")
        self.assertContains(response, "Clubfeest")

    def test_event_places(self):
        response = self.client.post("/shop/clubfeest/", {"qty": "4"})
        self.assertContains(response, "nog maar 3 plaatsen")
        self.client.post("/shop/clubfeest/", {"qty": "3"})
        self.checkout(email="vreemde@example.com")  # events zijn niet enkel voor leden
        self.assertEqual(self.feest.places_left, 0)
        self.assertContains(self.client.get("/shop/clubfeest/"), "Volzet")
        services.expire_pending(timezone.now() + timedelta(minutes=31))
        self.assertEqual(self.feest.places_left, 3)

    def test_event_only_order_needs_no_delivery(self):
        self.client.post("/shop/clubfeest/", {"qty": "2"})
        self.checkout()
        self.webhook("checkout.session.completed")
        order = Order.objects.get()
        self.assertEqual(order.status, Order.DELIVERED)
        self.assertEqual(order.total, Decimal("140"))
        self.assertEqual([m.to for m in mail.outbox], [["jan@example.com"]])  # geen mail naar de stock
        self.assertIn("inschrijving is in orde", mail.outbox[0].body)
        self.assertEqual(self.feest.places_taken, 2)

    def test_price_after_date(self):
        self.lidgeld.price_after_date = timezone.localdate()
        self.lidgeld.save()
        self.assertEqual(self.lidgeld.current_price(), Decimal("75"))
        self.assertEqual(self.lidgeld.current_price(timezone.localdate() - timedelta(days=1)), Decimal("65"))

    def member_data(self, first_name="Jan", national="80050112310"):
        return {"qty": "1", "q_0": national, "q_1": "Peeters", "q_2": first_name, "q_3": "Ieperstraat 1",
                "q_4": "8980", "q_5": "Zonnebeke", "q_6": "1980-05-01", "q_7": "Man", "q_8": "0470 12 34 56",
                "q_9": f"{first_name.lower()}@example.com"}

    def test_membership_kinds(self):
        self.assertEqual(
            list(Product.objects.filter(kind=Product.KIND_MEMBERSHIP).values_list("title", "price", "requires_main")),
            [("1e aansluiting", Decimal("65"), False), ("2e aansluiting", Decimal("65"), True),
             ("Gratis gezinsaansluiting", Decimal("0"), True)],
        )
        self.assertEqual(self.lidgeld.form.check_labels(), ["Geregistreerd bij VWB", "Betaald aan VWB"])

    def test_national_number_is_checked(self):
        response = self.client.post("/shop/lidgeld/", self.member_data(national="80050112300"))
        self.assertContains(response, "rijksregisternummer klopt niet")

    def test_membership_with_family_and_cyql_invite(self):
        self.lidgeld.price_after_date = timezone.localdate() + timedelta(days=30)
        self.lidgeld.save()
        self.assertRedirects(self.client.post("/shop/lidgeld/", self.member_data()), "/winkelmandje/")
        self.assertRedirects(
            self.client.post("/shop/gezinsaansluiting/", self.member_data("Lien", national="12031212313")),
            "/winkelmandje/",
        )
        response = self.client.get("/afrekenen/")
        self.assertContains(response, "akkoord met het clubreglement")
        with mock.patch("apps.shop.payments.create_checkout_session", return_value=fake_session()) as stripe:
            self.client.post("/afrekenen/", {"name": "Jan Peeters", "email": "nieuw@example.com",
                                             "phone": "0470 12 34 56", "accept": "on"})
        order = Order.objects.get()
        self.assertEqual(stripe.call_args.args[0], order)
        self.webhook("checkout.session.completed")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.DELIVERED)
        self.assertEqual(order.total, Decimal("65"))
        self.assertEqual(order.lines.count(), 2)
        invite = [m for m in mail.outbox if "Cyql" in m.subject]
        self.assertEqual(len(invite), 1)
        self.assertIn("https://cyql.example/uitnodiging", invite[0].body)
        submissions = list(self.lidgeld.form.submissions.order_by("pk"))
        self.assertEqual(len(submissions), 2)  # één per persoon
        self.assertEqual(submissions[0].order_number, order.number)
        self.assertIn(["Aansluiting", "1e aansluiting"], submissions[0].answers)
        self.assertIn(["Rijksregisternummer", "80.05.01-123.10"], submissions[0].answers)
        self.assertIn(["Telefoon", "+32470123456"], submissions[0].answers)
        self.assertIn(["Aansluiting", "Gratis gezinsaansluiting"], submissions[1].answers)
        self.assertIn(["Voornaam", "Lien"], submissions[1].answers)

    def test_family_needs_first_membership(self):
        self.client.post("/shop/gezinsaansluiting/", self.member_data("Lien", national="12031212313"))
        response = self.client.get("/winkelmandje/")
        self.assertContains(response, "kan enkel samen met een 1e aansluiting")
        self.assertNotContains(response, "/afrekenen/")
        self.assertRedirects(self.checkout(), "/winkelmandje/")
        self.assertFalse(Order.objects.exists())

    def test_two_members_are_two_lines(self):
        self.client.post("/shop/lidgeld/", self.member_data())
        self.client.post("/shop/2e-aansluiting/", self.member_data("An", national="85073003328"))
        self.client.post("/shop/2e-aansluiting/", self.member_data("An", national="85073003328"))  # dubbel: telt één keer
        self.assertEqual([item["qty"] for item in self.client.session["winkelmandje"]], [1, 1])

    def test_vwb_checks_in_answers_list(self):
        self.client.post("/shop/lidgeld/", self.member_data())
        self.checkout(email="nieuw@example.com")
        self.webhook("checkout.session.completed")
        submission = self.lidgeld.form.submissions.get()
        admin = get_user_model().objects.create_superuser("beheer", "beheer@example.com", "x" * 14)
        self.client.force_login(admin)
        url = f"/admin/formulieren/{self.lidgeld.form.pk}/antwoorden/"
        response = self.client.get(url)
        self.assertContains(response, "Geregistreerd bij VWB")
        self.assertContains(response, f'name="check-{submission.pk}-0"')
        self.client.post(url, {f"check-{submission.pk}-0": "on"})
        submission.refresh_from_db()
        self.assertEqual(submission.checks, {"Geregistreerd bij VWB": True, "Betaald aan VWB": False})
        export = self.client.get(f"/admin/formulieren/{self.lidgeld.form.pk}/export/")
        self.assertEqual(export.status_code, 200)

    def test_closed_event(self):
        self.feest.closes_at = timezone.now()
        self.feest.save()
        self.assertContains(self.client.get("/shop/clubfeest/"), "afgesloten")
        self.client.post("/shop/clubfeest/", {"qty": "1"})
        self.assertFalse(self.client.session.get("winkelmandje"))

    def test_participants_admin(self):
        self.client.post("/shop/clubfeest/", {"qty": "2"})
        self.checkout()
        self.webhook("checkout.session.completed")
        admin = get_user_model().objects.create_superuser("beheer", "beheer@example.com", "x" * 14)
        self.client.force_login(admin)
        response = self.client.get(f"/admin/webshop/deelnemers/{self.feest.pk}/")
        self.assertContains(response, "Jan Peeters")
        self.assertContains(response, "2 deelnemers")
        export = self.client.get(f"/admin/webshop/deelnemers/{self.feest.pk}/?export=1")
        self.assertEqual(export["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertContains(self.client.get("/admin/shop_products/"), "2 ingeschreven")

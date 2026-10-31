from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.core.models import Clubgegevens
from apps.formulieren.models import Form, Question
from apps.formulieren.services import save_submission
from apps.shop import services as shop
from apps.shop.models import Order, OrderLine, Product

from . import services
from .models import MailLog, MailTemplate
from .registry import MAILS
from .templatetags.mails import mask_national_number


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        club = Clubgegevens.load()
        club.email = "info@example.com"
        club.save()
        cls.lidgeld = Product.objects.get(slug="lidgeld")
        cls.admin = get_user_model().objects.create_superuser("beheer", "beheer@example.com", "x" * 14)

    def paid_membership_order(self):
        order = Order.objects.create(name="Jan Peeters", email="jan@example.com", total=Decimal("65"))
        OrderLine.objects.create(
            order=order, product=self.lidgeld, title="1e aansluiting", quantity=1, unit_price=Decimal("65"),
            answers=[["Rijksregisternummer", "80.05.01-123.10"], ["Naam", "Peeters"]],
        )
        shop.mark_paid(order, "pi_1")
        return order

    def test_mask(self):
        self.assertEqual(mask_national_number("80.05.01-123.10"), "80.05.01-•••.•• (volledig nummer in de beheeromgeving)")
        self.assertEqual(mask_national_number("Peeters"), "Peeters")

    def test_national_number_never_in_mails(self):
        self.lidgeld.form.notify_emails = "secretaris@example.com"
        self.lidgeld.form.save()
        self.paid_membership_order()
        self.assertGreaterEqual(len(mail.outbox), 3)  # bevestiging, welkom, melding
        for message in mail.outbox:
            self.assertNotIn("123.10", message.body)
        confirmation = next(m for m in mail.outbox if m.subject.startswith("Bevestiging bestelling"))
        self.assertIn("80.05.01-•••.••", confirmation.body)
        # Het volledige nummer blijft wel bewaard voor de beheerder.
        self.assertIn(["Rijksregisternummer", "80.05.01-123.10"], self.lidgeld.form.submissions.get().answers)

    def test_no_double_mail_to_club(self):
        self.lidgeld.form.notify_emails = "info@example.com\nsecretaris@example.com"
        self.lidgeld.form.save()
        self.paid_membership_order()
        to_club = [m for m in mail.outbox if "info@example.com" in m.to + m.cc]
        self.assertEqual([m.subject for m in to_club], [m.subject for m in to_club if m.subject.startswith("Bevestiging")])
        notify = next(m for m in mail.outbox if m.subject.startswith("Nieuw antwoord"))
        self.assertEqual(notify.to, ["secretaris@example.com"])

    def test_admin_texts_and_placeholders(self):
        template = MailTemplate.get("order_confirmation")
        template.subject = "Merci {naam}: {bestelnummer}"
        template.outro = "Tot op de clubrit, {onbekend}."
        template.save()
        order = self.paid_membership_order()
        message = mail.outbox[0]
        self.assertEqual(message.subject, f"Merci Jan Peeters: {order.number}")
        self.assertIn("Tot op de clubrit, {onbekend}.", message.body)
        self.assertIn("WTC Zonnebeke vzw", message.body)  # gegevens van de club onderaan

    def test_disabled_mail_is_not_sent(self):
        template = MailTemplate.get("membership_welcome")
        template.enabled = False
        template.save()
        self.paid_membership_order()
        self.assertFalse(any("Cyql" in m.subject for m in mail.outbox))

    def test_copy_address_setting(self):
        club = Clubgegevens.load()
        club.mail_copy_to = "penningmeester@example.com"
        club.save()
        self.paid_membership_order()
        self.assertEqual(mail.outbox[0].cc, ["penningmeester@example.com"])

    def test_extra_text_per_event(self):
        self.lidgeld.confirmation_text = "Je lidkaart krijg je op de eerste clubrit."
        self.lidgeld.save()
        self.paid_membership_order()
        self.assertIn("Je lidkaart krijg je op de eerste clubrit.", mail.outbox[0].body)

    def test_form_confirmation_can_be_switched_off(self):
        form = Form.objects.create(title="Vrijwilligers", notify_emails="", send_confirmation=False)
        Question.objects.create(form=form, label="E-mail", kind=Question.EMAIL)
        save_submission(form, [["E-mail", "an@example.com"]], email="an@example.com")
        self.assertEqual(mail.outbox, [])

    def test_log_and_resend(self):
        order = self.paid_membership_order()
        entry = MailLog.objects.get(key="order_confirmation")
        self.assertTrue(entry.ok)
        self.assertEqual(entry.object_id, order.pk)
        self.assertIn("kopie: info@example.com", entry.recipients)
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=RuntimeError("Graph weg")):
            shop.send_ready_mail(order)
        failed = MailLog.objects.get(ok=False)
        self.assertIn("Graph weg", failed.error)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/admin/e-mails/verstuurd/?mislukt=1"), "Graph weg")
        mail.outbox.clear()
        self.client.post(f"/admin/e-mails/verstuurd/{failed.pk}/opnieuw/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ligt klaar", mail.outbox[0].subject)

    def test_admin_pages(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/e-mails/")
        for spec in MAILS.values():
            self.assertContains(response, spec.label)
        self.assertContains(response, "Contactformulier")
        url = "/admin/e-mails/order_confirmation/"
        self.assertContains(self.client.get(url), "Bestelling 2026-0042")  # voorbeeld
        data = {"subject": "Nieuw onderwerp {bestelnummer}", "intro": "Dag {naam}", "outro": "", "enabled": "on",
                "copy_to_club": "on"}
        response = self.client.post(url, {**data, "action": "preview"})
        self.assertContains(response, "Nieuw onderwerp 2026-0042")
        self.assertEqual(MailTemplate.get("order_confirmation").subject, "Bevestiging bestelling {bestelnummer}")
        self.client.post(url, {**data, "action": "test"})
        self.assertEqual(mail.outbox[-1].to, ["beheer@example.com"])
        self.assertTrue(mail.outbox[-1].subject.startswith("[TEST]"))
        self.client.post(url, {**data, "action": "save"})
        self.assertEqual(MailTemplate.get("order_confirmation").subject, "Nieuw onderwerp {bestelnummer}")
        self.client.post(url, {"action": "reset"})
        self.assertEqual(MailTemplate.get("order_confirmation").subject, "Bevestiging bestelling {bestelnummer}")

    def test_admin_pages_need_superuser(self):
        user = get_user_model().objects.create_user("stock", "stock@example.com", "x" * 14, is_staff=True)
        self.client.force_login(user)
        self.assertNotEqual(self.client.get("/admin/e-mails/").status_code, 200)

    def test_every_mail_renders_with_sample(self):
        from .registry import sample_context

        for key, spec in MAILS.items():
            with self.subTest(key=key):
                subject, body = services.render(key, sample_context(spec))
                self.assertNotIn("{", subject)
                self.assertNotIn("123.10", body)

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import load_workbook

from .models import Form, Question, Submission, normalize_be_phone, visible_questions


def make_form(**kwargs):
    form = Form.objects.create(title="Vrijwilligers WaCaCa", notify_emails="secretaris@example.com", **kwargs)
    questions = [
        ("Naam", Question.TEXT, True, "", "", None),
        ("E-mailadres", Question.EMAIL, True, "", "", None),
        ("Gsm", Question.PHONE, True, "", "", None),
        ("Kom je helpen?", Question.CHOICE, True, "Ja\nNee", "Nee", 0),
        ("Welke shift?", Question.CHOICES_MULTI, True, "Voormiddag\nNamiddag", "", None),
    ]
    for position, (label, kind, required, choices, jump_answer, jump_to) in enumerate(questions):
        Question.objects.create(form=form, sort_order=position, label=label, kind=kind, required=required,
                                choices=choices, jump_answer=jump_answer, jump_to=jump_to)
    return form


class HelperTests(TestCase):
    def test_phone(self):
        self.assertEqual(normalize_be_phone("0470 12 34 56"), "+32470123456")
        self.assertEqual(normalize_be_phone("+32 470/12.34.56"), "+32470123456")
        self.assertEqual(normalize_be_phone("0032 51 12 34 56"), "+3251123456")
        self.assertIsNone(normalize_be_phone("12345"))
        self.assertIsNone(normalize_be_phone("+33612345678"))

    def test_jumps(self):
        form = make_form()
        questions = list(form.questions.all())
        self.assertEqual(visible_questions(questions, {3: "Ja"}), [0, 1, 2, 3, 4])
        self.assertEqual(visible_questions(questions, {3: "Nee"}), [0, 1, 2, 3])


@override_settings(TURNSTILE_SECRET_KEY="", TURNSTILE_SITE_KEY="")
class PublicFormTests(TestCase):
    def setUp(self):
        self.form = make_form(one_per_email=True)
        self.url = self.form.get_absolute_url()

    def post(self, **extra):
        data = {"q_0": "An Peeters", "q_1": "An@Example.com", "q_2": "0470 12 34 56", "q_3": "Ja", "q_4": ["Namiddag"]}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_render_noindex(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Kom je helpen?")
        self.assertContains(response, 'data-jump-to="0"')
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_submit_and_mails(self):
        from apps.core.models import Clubgegevens

        club = Clubgegevens.load()
        club.email = "info@example.com"
        club.save()
        response = self.post()
        self.assertRedirects(response, f"{self.url}bedankt/")
        submission = Submission.objects.get()
        self.assertEqual(submission.email, "an@example.com")
        self.assertIn(["Gsm", "+32470123456"], submission.answers)
        self.assertIn(["Welke shift?", "Namiddag"], submission.answers)
        self.assertEqual([m.to for m in mail.outbox], [["an@example.com"], ["secretaris@example.com"]])
        self.assertEqual(mail.outbox[0].cc, ["info@example.com"])  # bevestiging in kopie naar de club

    def test_jump_skips_required_question(self):
        response = self.post(q_3="Nee", q_4=[])
        self.assertEqual(response.status_code, 302)
        labels = [label for label, _ in Submission.objects.get().answers]
        self.assertNotIn("Welke shift?", labels)

    def test_validation(self):
        response = self.post(q_2="123")
        self.assertContains(response, "geldig Belgisch nummer")
        response = self.post(q_4=[])
        self.assertContains(response, "verplicht veld")
        self.assertFalse(Submission.objects.exists())

    def test_one_per_email(self):
        self.post()
        response = self.post()
        self.assertContains(response, "al ingevuld")
        self.assertEqual(Submission.objects.count(), 1)

    def test_honeypot(self):
        self.post(website="spam")
        self.assertFalse(Submission.objects.exists())

    def test_closed(self):
        self.form.closes_at = timezone.now()
        self.form.save()
        self.assertContains(self.client.get(self.url), "afgesloten")
        self.post()
        self.assertFalse(Submission.objects.exists())

    def test_turnstile_required_when_configured(self):
        with override_settings(TURNSTILE_SECRET_KEY="geheim", TURNSTILE_SITE_KEY="sitekey"):
            response = self.client.get(self.url)
            self.assertIn("challenges.cloudflare.com", response["Content-Security-Policy"])
            response = self.post()
            self.assertContains(response, "geen robot")

    def test_admin_answers_and_export(self):
        self.post()
        admin = get_user_model().objects.create_superuser("beheer", "beheer@example.com", "x" * 14)
        self.client.force_login(admin)
        self.assertContains(self.client.get(f"/admin/formulieren/{self.form.pk}/antwoorden/"), "An Peeters")
        response = self.client.get(f"/admin/formulieren/{self.form.pk}/export/")
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["D1"].value, "Naam")
        self.assertEqual(sheet["D2"].value, "An Peeters")
        self.assertContains(self.client.get("/admin/formulieren/"), "1 antwoord")

    def test_admin_only_for_superusers(self):
        user = get_user_model().objects.create_user("lid", "lid@example.com", is_staff=True)
        self.client.force_login(user)
        self.assertNotEqual(self.client.get(f"/admin/formulieren/{self.form.pk}/export/").status_code, 200)


class NationalNumberTests(TestCase):
    def test_check_digits(self):
        from .models import normalize_national_number

        self.assertEqual(normalize_national_number("85073003328"), "85.07.30-033.28")
        self.assertEqual(normalize_national_number("85.07.30-033.28"), "85.07.30-033.28")
        self.assertEqual(normalize_national_number("12031212313"), "12.03.12-123.13")  # geboren na 2000
        self.assertIsNone(normalize_national_number("85073003329"))
        self.assertIsNone(normalize_national_number("8507300332"))

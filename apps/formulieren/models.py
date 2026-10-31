"""Formulierenbouwer: eigen formulieren met sprongregels, ook gebruikt voor de extra vragen bij inschrijvingen.

Een formulier staat op /formulier/<code>/. Wie de link heeft, kan antwoorden; de pagina is niet gelinkt
en niet geïndexeerd. Antwoorden bekijk en exporteer je in de beheeromgeving.
"""

import re
import secrets

from django.db import models
from django.utils import timezone
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable

from apps.core.models import parse_emails


def new_code():
    return secrets.token_urlsafe(9)


class Form(ClusterableModel):
    title = models.CharField("titel", max_length=150)
    code = models.SlugField(
        "geheime code",
        max_length=40,
        unique=True,
        default=new_code,
        help_text="Het formulier staat op /formulier/<code>/. Wijzig de code om een oude link onbruikbaar te maken.",
    )
    intro = RichTextField("inleiding", blank=True, features=["bold", "italic", "link", "ol", "ul"])
    thanks = models.TextField(
        "bedankt-tekst", default="Bedankt! We hebben je antwoorden goed ontvangen.",
        help_text="Op het scherm en in de bevestigingsmail.",
    )
    closes_at = models.DateTimeField("sluit op", null=True, blank=True, help_text="Leeg: blijft open.")
    is_active = models.BooleanField("open voor antwoorden", default=True)
    one_per_email = models.BooleanField(
        "één antwoord per e-mailadres", default=False, help_text="Werkt als het formulier een vraag van het type e-mail heeft."
    )
    send_confirmation = models.BooleanField(
        "bevestiging sturen", default=True,
        help_text="De invuller krijgt een mail met de bedankt-tekst en de antwoorden (als er een vraag van het type e-mail is).",
    )
    notify_emails = models.TextField(
        "meldingen naar", blank=True, help_text="Eén e-mailadres per lijn. Krijgt elk nieuw antwoord in de mailbox."
    )
    admin_checks = models.TextField(
        "afvinken door de beheerder", blank=True,
        help_text="Eén vakje per lijn, bv. Geregistreerd bij VWB. Je vinkt ze per antwoord af in de lijst met antwoorden.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    panels = [
        MultiFieldPanel([FieldPanel("title"), FieldPanel("code"), FieldPanel("intro"), FieldPanel("thanks")], heading="Formulier"),
        MultiFieldPanel(
            [FieldRowPanel([FieldPanel("is_active"), FieldPanel("closes_at")]), FieldPanel("one_per_email"), FieldPanel("send_confirmation"), FieldPanel("notify_emails"),
             FieldPanel("admin_checks")],
            heading="Instellingen",
        ),
        InlinePanel(
            "questions",
            heading="Vragen",
            label="vraag",
            help_text="De vragen zijn genummerd in deze volgorde (1, 2, 3 ...). Een sprongregel verwijst naar dat nummer.",
        ),
    ]

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "formulier"
        verbose_name_plural = "formulieren"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/formulier/{self.code}/"

    @property
    def is_open(self):
        return self.is_active and (self.closes_at is None or self.closes_at > timezone.now())

    def numbered_questions(self):
        return list(self.questions.all())

    def notify_addresses(self):
        return sorted(parse_emails(self.notify_emails))

    def check_labels(self):
        return [line.strip() for line in self.admin_checks.splitlines() if line.strip()]


class Question(Orderable):
    TEXT = "tekst"
    TEXTAREA = "lange_tekst"
    EMAIL = "email"
    PHONE = "gsm"
    DATE = "datum"
    NATIONAL_NUMBER = "rijksregister"
    CHOICE = "keuze"
    CHOICES_MULTI = "keuzes"
    KINDS = [
        (TEXT, "Tekst (één lijn)"),
        (TEXTAREA, "Lange tekst"),
        (EMAIL, "E-mailadres"),
        (PHONE, "Gsm-nummer (België)"),
        (DATE, "Datum"),
        (NATIONAL_NUMBER, "Rijksregisternummer"),
        (CHOICE, "Meerkeuze: één antwoord"),
        (CHOICES_MULTI, "Meerkeuze: meerdere antwoorden"),
    ]

    form = ParentalKey(Form, on_delete=models.CASCADE, related_name="questions")
    label = models.CharField("vraag", max_length=255)
    kind = models.CharField("soort", max_length=20, choices=KINDS, default=TEXT)
    required = models.BooleanField("verplicht", default=True)
    help_text = models.CharField("uitleg", max_length=255, blank=True)
    choices = models.TextField("keuzes", blank=True, help_text="Enkel bij meerkeuze: één keuze per lijn.")
    jump_answer = models.CharField(
        "als het antwoord is", max_length=255, blank=True, help_text="Sprongregel, enkel bij meerkeuze: één van de keuzes."
    )
    jump_to = models.PositiveIntegerField(
        "ga dan naar vraag nr.", null=True, blank=True, help_text="0 = naar het einde van het formulier."
    )

    panels = [
        FieldRowPanel([FieldPanel("label"), FieldPanel("kind"), FieldPanel("required")]),
        FieldPanel("help_text"),
        FieldPanel("choices"),
        FieldRowPanel([FieldPanel("jump_answer"), FieldPanel("jump_to")]),
    ]

    class Meta(Orderable.Meta):
        verbose_name = "vraag"
        verbose_name_plural = "vragen"

    def __str__(self):
        return self.label

    def choice_list(self):
        return [line.strip() for line in self.choices.splitlines() if line.strip()]


class Submission(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="submissions")
    answers = models.JSONField("antwoorden", default=list, help_text="Lijst van [vraag, antwoord].")
    email = models.EmailField("e-mailadres", blank=True, db_index=True)
    order_number = models.CharField("bestelling", max_length=20, blank=True)
    checks = models.JSONField("afgevinkt", default=dict, blank=True, help_text="Per vakje: aangevinkt of niet.")
    created_at = models.DateTimeField("ingediend op", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "antwoord"
        verbose_name_plural = "antwoorden"

    def __str__(self):
        return f"{self.form} {self.created_at:%d/%m/%Y %H:%M}"


# ------------------------------------------------------------------ hulpfuncties

PHONE_CLEAN = re.compile(r"[\s./()-]")


def normalize_be_phone(value):
    """Belgisch nummer naar +32-formaat, of None als het geen geldig nummer is."""
    number = PHONE_CLEAN.sub("", value or "")
    if number.startswith("0032"):
        number = "+32" + number[4:]
    elif number.startswith("0"):
        number = "+32" + number[1:]
    if re.fullmatch(r"\+32[1-9]\d{7,8}", number):
        return number
    return None


def normalize_national_number(value):
    """Belgisch rijksregisternummer naar JJ.MM.DD-XXX.CC, of None als de controlegetallen niet kloppen."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 11:
        return None
    base, check = int(digits[:9]), int(digits[9:])
    # Geboren vanaf 2000: er komt een 2 voor de eerste negen cijfers.
    if check not in (97 - base % 97, 97 - (2_000_000_000 + base) % 97):
        return None
    return f"{digits[0:2]}.{digits[2:4]}.{digits[4:6]}-{digits[6:9]}.{digits[9:11]}"


def visible_questions(questions, answers):
    """Volgt de sprongregels: welke vragen krijgt deze invuller te zien?

    `answers` geeft per vraag-index het antwoord (tekst of lijst). Vragen zijn genummerd vanaf 1.
    """
    visible = []
    index = 0
    seen = set()
    while 0 <= index < len(questions) and index not in seen:
        seen.add(index)
        question = questions[index]
        visible.append(index)
        target = None
        answer = answers.get(index)
        if question.jump_answer and question.jump_to is not None:
            given = answer if isinstance(answer, list) else [answer]
            if question.jump_answer.strip() in [str(a).strip() for a in given if a]:
                target = question.jump_to
        if target is None:
            index += 1
        elif target == 0:
            break
        else:
            index = max(target - 1, index + 1)  # nooit terug springen
    return visible


def _admin_links(form):
    from django.urls import reverse
    from django.utils.html import format_html

    count = form.submissions.count()
    return format_html(
        '<a href="{}">{} antwoord{}</a> · <a href="{}">Excel</a>',
        reverse("formulier_antwoorden", args=[form.pk]), count, "" if count == 1 else "en",
        reverse("formulier_export", args=[form.pk]),
    )


Form.answers_link = _admin_links
Form.answers_link.short_description = "antwoorden"

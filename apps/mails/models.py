"""Automatische e-mails: teksten die een beheerder zelf aanpast, en een logboek van wat verstuurd is.

Welke mails er bestaan, wanneer ze vertrekken en naar wie, staat vast in `registry.py`.
De standaardteksten komen in de database zodra een mail voor het eerst nodig is;
daarna overschrijft niets ze nog (ook geen redeploy).
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

LOG_DAYS = 90


class MailTemplate(models.Model):
    key = models.CharField("mail", max_length=40, unique=True)
    subject = models.CharField("onderwerp", max_length=200)
    intro = models.TextField("tekst boven", blank=True, help_text="Aanhef en uitleg, boven de gegevens.")
    outro = models.TextField("tekst onder", blank=True, help_text="Afsluiter, onder de gegevens.")
    enabled = models.BooleanField("versturen", default=True, help_text="Uit: deze mail wordt niet meer verstuurd.")
    copy_to_club = models.BooleanField(
        "kopie naar de club", default=False,
        help_text="Een kopie gaat naar het adres bij Instellingen > Clubgegevens > kopie van klantmails.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "e-mailtekst"
        verbose_name_plural = "e-mailteksten"

    def __str__(self):
        from .registry import MAILS

        return MAILS[self.key].label if self.key in MAILS else self.key

    @classmethod
    def get(cls, key):
        """De tekst van een mail; bestaat ze nog niet, dan komt de standaardtekst in de database."""
        from .registry import MAILS

        spec = MAILS[key]
        template, _ = cls.objects.get_or_create(key=key, defaults=spec.defaults())
        return template

    def reset(self):
        from .registry import MAILS

        for field, value in MAILS[self.key].defaults().items():
            setattr(self, field, value)
        self.save()


class MailLog(models.Model):
    created_at = models.DateTimeField("verstuurd op", auto_now_add=True, db_index=True)
    key = models.CharField("mail", max_length=40)
    recipients = models.TextField("naar")
    subject = models.CharField("onderwerp", max_length=255)
    ok = models.BooleanField("gelukt", default=True)
    error = models.TextField("fout", blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True, help_text="Bestelling of antwoord, om opnieuw te versturen.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "verstuurde mail"
        verbose_name_plural = "verstuurde mails"

    @classmethod
    def clean_up(cls):
        cls.objects.filter(created_at__lt=timezone.now() - timedelta(days=LOG_DAYS)).delete()

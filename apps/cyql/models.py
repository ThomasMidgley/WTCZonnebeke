from django.db import models


class SyncRun(models.Model):
    """Eén synchronisatie met Cyql, zodat de beheerder ziet of de nachtelijke sync gelukt is."""

    started_at = models.DateTimeField("gestart", auto_now_add=True)
    finished_at = models.DateTimeField("klaar", null=True, blank=True)
    ok = models.BooleanField("gelukt", default=False)
    message = models.TextField("verslag", blank=True)
    remaining_budget = models.IntegerField("resterend weekbudget", null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Cyql-synchronisatie"
        verbose_name_plural = "Cyql-synchronisaties"

    def __str__(self):
        return f"{self.started_at:%d/%m/%Y %H:%M} ({'gelukt' if self.ok else 'mislukt'})"


class ClubStats(models.Model):
    """Kerncijfers van de club uit Cyql, bijgewerkt bij elke synchronisatie."""

    member_count = models.PositiveIntegerField("aantal leden", null=True, blank=True)
    updated_at = models.DateTimeField("bijgewerkt", auto_now=True)

    class Meta:
        verbose_name = "clubcijfers"

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

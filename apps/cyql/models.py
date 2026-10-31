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


class Ride(models.Model):
    """Geplande clubrit uit Cyql. Bij elke sync volledig vervangen door de komende ritten."""

    cyql_id = models.UUIDField(unique=True)
    title = models.CharField("titel", max_length=255)
    start_time = models.DateTimeField("vertrek")
    location = models.CharField("vertrekplaats", max_length=255, blank=True)
    distance = models.FloatField("afstand (km)", null=True, blank=True)
    average_speed = models.FloatField("gemiddelde (km/u)", null=True, blank=True)
    ride_type = models.CharField("soort", max_length=20, blank=True)
    labels = models.CharField("labels", max_length=255, blank=True)
    share_url = models.URLField("link in Cyql", max_length=500, blank=True)
    gpx_url = models.URLField("GPX", max_length=500, blank=True)

    class Meta:
        ordering = ["start_time"]
        verbose_name = "rit"
        verbose_name_plural = "ritten"

    def __str__(self):
        return f"{self.start_time:%d/%m/%Y} {self.title}"

    @property
    def label_list(self):
        return [label for label in self.labels.split(", ") if label]


class ClubEvent(models.Model):
    """Agendapunt uit Cyql (geen rit): vergadering, feest, ..."""

    cyql_id = models.UUIDField(unique=True)
    title = models.CharField("titel", max_length=255)
    start_time = models.DateTimeField("begin")
    end_time = models.DateTimeField("einde", null=True, blank=True)
    location = models.CharField("plaats", max_length=255, blank=True)

    class Meta:
        ordering = ["start_time"]
        verbose_name = "activiteit"
        verbose_name_plural = "activiteiten"

    def __str__(self):
        return self.title


class Challenge(models.Model):
    """Klassement (challenge) in Cyql. Beheerders kiezen welke op de website komen."""

    SCORE_UNITS = {"DISTANCE": "km", "SCORE": "punten", "NUMBER_OF_RIDES": "ritten"}

    cyql_id = models.UUIDField(unique=True)
    title = models.CharField("titel", max_length=255)
    score_type = models.CharField("soort score", max_length=20, blank=True)
    start_date = models.DateTimeField("begin", null=True, blank=True)
    end_date = models.DateTimeField("einde", null=True, blank=True)
    participant_count = models.PositiveIntegerField("deelnemers", null=True, blank=True)
    is_active = models.BooleanField("actief in Cyql", default=True)
    show_on_site = models.BooleanField(
        "tonen op de website", default=True, help_text="Enkel getoonde klassementen kosten API-budget bij de sync."
    )
    sort_order = models.PositiveIntegerField("volgorde", default=0)
    scores_updated_at = models.DateTimeField("scores bijgewerkt", null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "-start_date"]
        verbose_name = "klassement"
        verbose_name_plural = "klassementen"

    def __str__(self):
        return self.title

    @property
    def unit(self):
        return self.SCORE_UNITS.get(self.score_type, "")


class ChallengeScore(models.Model):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="scores")
    rank = models.PositiveIntegerField("plaats")
    member_name = models.CharField("naam", max_length=255)
    score = models.FloatField("score")
    ride_count = models.PositiveIntegerField("ritten", null=True, blank=True)

    class Meta:
        ordering = ["rank", "member_name"]

    @property
    def short_name(self):
        """Voornaam en initiaal van de familienaam: genoeg voor leden, beperkt voor de buitenwereld."""
        first, _, last = self.member_name.strip().partition(" ")
        return f"{first} {last[0]}." if last else first


class Member(models.Model):
    """Goedgekeurd lid in Cyql, voor de lidcontrole bij inschrijvingen en in de webshop."""

    cyql_id = models.UUIDField(unique=True)
    first_name = models.CharField("voornaam", max_length=120)
    last_name = models.CharField("familienaam", max_length=120)
    email = models.EmailField("e-mailadres", blank=True, db_index=True)
    status = models.CharField("status", max_length=20)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "lid"
        verbose_name_plural = "leden"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @classmethod
    def is_member(cls, email):
        return bool(email) and cls.objects.filter(email__iexact=email.strip()).exists()

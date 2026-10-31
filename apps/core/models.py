import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from wagtail.admin.panels import FieldPanel, HelpPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting

from . import colors

hex_validator = RegexValidator(colors.HEX_RE, "Gebruik een HEX-kleurcode zoals #FF5200.")


def parse_emails(text):
    return {line.strip().lower() for line in text.replace(",", "\n").splitlines() if line.strip()}


@register_setting(icon="image", order=10)
class Huisstijl(BaseGenericSetting):
    primary_color = models.CharField(
        "basiskleur",
        max_length=7,
        default="#231F20",
        validators=[hex_validator],
        help_text="Kop- en voettekst, titels. Witte tekst moet erop leesbaar zijn.",
    )
    accent_color = models.CharField(
        "accentkleur",
        max_length=7,
        default="#FF5200",
        validators=[hex_validator],
        help_text="Knoppen en markeringen. Voor tekstlinks wordt automatisch een leesbare tint berekend.",
    )

    panels = [FieldPanel("primary_color"), FieldPanel("accent_color")]

    class Meta:
        verbose_name = "huisstijl"

    def clean(self):
        super().clean()
        errors = {}
        if colors.HEX_RE.match(self.primary_color or "") and colors.contrast(self.primary_color, "#FFFFFF") < 4.5:
            errors["primary_color"] = (
                f"Te licht: witte tekst haalt maar {colors.contrast(self.primary_color, '#FFFFFF'):.1f}:1 "
                "contrast (minimum 4,5:1). Kies een donkerdere kleur."
            )
        if colors.HEX_RE.match(self.accent_color or ""):
            on_accent = colors.readable_on(self.accent_color)
            if colors.contrast(self.accent_color, on_accent) < 3:
                errors["accent_color"] = "Op deze kleur is geen enkele tekstkleur goed leesbaar. Kies een andere."
        if errors:
            raise ValidationError(errors)

    @property
    def css_variables(self):
        accent_text = colors.darken_until(self.accent_color)
        return {
            "--primary": self.primary_color,
            "--on-primary": "#FFFFFF",
            "--accent": self.accent_color,
            "--on-accent": colors.readable_on(self.accent_color),
            "--accent-text": accent_text,
        }


@register_setting(icon="home", order=20)
class Clubgegevens(BaseGenericSetting):
    vzw_name = models.CharField("naam vzw", max_length=120, default="WTC Zonnebeke vzw")
    address = models.CharField("maatschappelijke zetel", max_length=200, blank=True)
    enterprise_number = models.CharField("ondernemingsnummer", max_length=40, blank=True)
    rpr = models.CharField("RPR", max_length=80, blank=True)
    iban = models.CharField("rekeningnummer (IBAN)", max_length=40, blank=True)
    email = models.EmailField("e-mailadres", blank=True)
    phone = models.CharField("telefoon", max_length=40, blank=True)
    meeting_place = models.CharField("vertrekplaats clubritten", max_length=200, blank=True)
    facebook_url = models.URLField("Facebook", blank=True)
    strava_url = models.URLField("Strava", blank=True)
    privacy_url = models.URLField("privacyverklaring", blank=True)

    panels = [
        MultiFieldPanel(
            [FieldPanel("vzw_name"), FieldPanel("address"), FieldPanel("enterprise_number"), FieldPanel("rpr")],
            heading="Vzw",
        ),
        MultiFieldPanel(
            [FieldPanel("iban"), FieldPanel("email"), FieldPanel("phone"), FieldPanel("meeting_place")],
            heading="Contact",
        ),
        MultiFieldPanel(
            [FieldPanel("facebook_url"), FieldPanel("strava_url"), FieldPanel("privacy_url")],
            heading="Links",
        ),
    ]

    class Meta:
        verbose_name = "clubgegevens"


@register_setting(icon="doc-full", order=30)
class Clubreglement(BaseGenericSetting):
    document = models.ForeignKey(
        "wagtaildocs.Document",
        verbose_name="clubreglement (Word of PDF)",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Wordt als download aangeboden op de pagina Clubreglement. "
        "De tekst op de webpagina zelf pas je aan via Pagina's > Clubreglement.",
    )

    panels = [FieldPanel("document")]

    class Meta:
        verbose_name = "clubreglement"


@register_setting(icon="link-external", order=40)
class Statuten(BaseGenericSetting):
    url = models.URLField("link naar de vzw-statuten", blank=True)

    panels = [FieldPanel("url")]

    class Meta:
        verbose_name = "vzw-statuten"


@register_setting(icon="resubmit", order=50)
class CyqlApp(BaseGenericSetting):
    """Instellingen voor Cyql. Staan in het menu Cyql, niet bij Instellingen."""

    invite_link = models.URLField(
        "uitnodigingslink Cyql-app",
        default="https://cyqlapp.app.link/vn8stXATsXb",
        help_text="De QR-code op de Cyql-pagina wordt automatisch uit deze link gemaakt.",
    )
    sync_time = models.TimeField(
        "synchroniseren om", default=datetime.time(3, 0), help_text="Eén keer per nacht; geldt meteen."
    )
    event_url = models.CharField(
        "link naar een activiteit",
        max_length=255,
        blank=True,
        help_text="Cyql geeft geen link per activiteit mee. Open een activiteit op web.cyql.app, kopieer het adres "
        "en vervang het laatste deel (de code van die activiteit) door {id}, bv. "
        "https://web.cyql.app/events/view/&lt;club&gt;/{id}. Leeg: de knop verwijst naar de pagina Cyql-app.",
    )

    panels = [
        HelpPanel(content="<p>De API-sleutel staat niet hier maar in Portainer als <code>CYQL_API_KEY</code>.</p>"),
        FieldPanel("sync_time"),
        FieldPanel("invite_link"),
        FieldPanel("event_url"),
    ]

    class Meta:
        verbose_name = "Cyql-instellingen"

    def event_link(self, cyql_id):
        return self.event_url.replace("{id}", str(cyql_id)) if "{id}" in self.event_url else ""


@register_setting(icon="cogs", order=60)
class Integraties(BaseGenericSetting):
    azure_tenant_id = models.CharField("tenant-ID", max_length=64, blank=True)
    azure_client_id = models.CharField("application (client) ID", max_length=64, blank=True)
    mail_sender = models.EmailField(
        "afzender bevestigingsmails", default="info@wtczonnebeke.be", help_text="Mailbox in dezelfde tenant."
    )
    stripe_publishable_key = models.CharField("Stripe publishable key", max_length=255, blank=True)

    panels = [
        HelpPanel(
            content="<p>Geheimen (client secret, Cyql API-sleutel, Stripe secret key, webhook-geheim) "
            "staan <strong>niet</strong> hier maar als omgevingsvariabelen in Portainer: "
            "<code>AZURE_CLIENT_SECRET</code>, <code>CYQL_API_KEY</code>, <code>STRIPE_SECRET_KEY</code>, "
            "<code>STRIPE_WEBHOOK_SECRET</code>.</p>"
        ),
        MultiFieldPanel(
            [FieldPanel("azure_tenant_id"), FieldPanel("azure_client_id"), FieldPanel("mail_sender")],
            heading="Microsoft 365 (aanmelden en e-mail)",
        ),
        MultiFieldPanel([FieldPanel("stripe_publishable_key")], heading="Stripe"),
    ]

    class Meta:
        verbose_name = "integraties"

    @property
    def tenant_id(self):
        return self.azure_tenant_id or settings.AZURE_TENANT_ID

    @property
    def client_id(self):
        return self.azure_client_id or settings.AZURE_CLIENT_ID


@register_setting(icon="lock", order=70)
class Toegang(BaseGenericSetting):
    admin_emails = models.TextField(
        "beheerders",
        blank=True,
        help_text="Eén Microsoft 365-adres per regel. Beheerders kunnen alles aanpassen.",
    )
    stock_emails = models.TextField(
        "stockbeheerders",
        blank=True,
        help_text="Eén Microsoft 365-adres per regel. Stockbeheerders zien enkel bestellingen en stock.",
    )

    panels = [
        HelpPanel(
            content="<p>Wie hier niet vermeld staat, kan niet inloggen. "
            "Wijzigingen gelden vanaf de volgende keer dat iemand inlogt.</p>"
        ),
        FieldPanel("admin_emails"),
        FieldPanel("stock_emails"),
    ]

    class Meta:
        verbose_name = "toegang"

    def stock_addresses(self):
        """Wie mails over nieuwe bestellingen krijgt: de stockbeheerders."""
        return parse_emails(self.stock_emails)

    def role_for(self, email):
        email = (email or "").strip().lower()
        admins = parse_emails(self.admin_emails) | {e.lower() for e in settings.BOOTSTRAP_ADMIN_EMAILS}
        if email in admins:
            return "beheerder"
        if email in parse_emails(self.stock_emails):
            return "stockbeheerder"
        return None


@register_setting(icon="pick", order=80)
class QrInfo(BaseGenericSetting):
    heading = models.CharField("titel", max_length=80, default="EVENEMENTEN QR INFO")
    greeting = models.CharField("aanhef", max_length=80, default="Hallo,")
    ownership = models.CharField(
        "eigendom", max_length=200, default="deze pijlen zijn eigendom van wtc-zonnebeke.be (VZW)"
    )
    report_text = models.CharField(
        "melding",
        max_length=200,
        default="Is een pijltje na een evenement blijven hangen? Verwittig aub de vereniging op het gsm-nummer",
    )
    report_phone = models.CharField("gsm-nummer vereniging", max_length=40, default="0478 27 67 85")
    event = models.CharField(
        "evenement", max_length=120, default="WaCaCa (Wattenberg - Casselberg - Catsberg)"
    )
    event_date = models.DateField("datum", null=True, blank=True)
    responsible = models.CharField("verantwoordelijke", max_length=120, default="Vandermeiren Frankie")
    responsible_phone = models.CharField("gsm verantwoordelijke", max_length=40, default="+32 475 60 82 00")
    organiser = models.CharField("organisator", max_length=120, default="WTC Zonnebeke VZW")

    panels = [
        HelpPanel(
            content="<p>Deze info verschijnt op <code>/index.php?id=900</code>, het adres in de QR-codes "
            "op de pijltjes. De weekdag wordt automatisch uit de datum berekend.</p>"
        ),
        FieldPanel("heading"),
        FieldPanel("greeting"),
        FieldPanel("ownership"),
        FieldPanel("report_text"),
        FieldPanel("report_phone"),
        FieldPanel("event"),
        FieldPanel("event_date"),
        FieldPanel("responsible"),
        FieldPanel("responsible_phone"),
        FieldPanel("organiser"),
    ]

    class Meta:
        verbose_name = "QR-info pijltjes"


class Sponsor(models.Model):
    name = models.CharField("naam", max_length=120)
    url = models.URLField("website", blank=True)
    logo = models.ForeignKey(
        "wagtailimages.Image", verbose_name="logo", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_main = models.BooleanField("hoofdsponsor", default=False, help_text="Hoofdsponsors staan prominent op de home.")
    is_visible = models.BooleanField("zichtbaar", default=True)
    sort_order = models.PositiveIntegerField("volgorde", default=0)

    panels = [
        FieldPanel("name"),
        FieldPanel("url"),
        FieldPanel("logo"),
        FieldPanel("is_main"),
        FieldPanel("is_visible"),
        FieldPanel("sort_order"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "sponsor"
        verbose_name_plural = "sponsors"

    def __str__(self):
        return self.name

import datetime
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from wagtail.admin.panels import FieldPanel, HelpPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting

from . import colors

hex_validator = RegexValidator(colors.HEX_RE, "Gebruik een HEX-kleurcode zoals #FF5200.")


SVG_UNSAFE = re.compile(r"<script|javascript:|\son[a-z]+\s*=|<foreignobject|<iframe|<embed|<object")


def validate_logo(file):
    """Een SVG-logo mag geen scripts bevatten."""
    if not file.name.lower().endswith(".svg"):
        return
    file.seek(0)
    content = file.read().decode("utf-8", "ignore").lower()
    file.seek(0)
    if SVG_UNSAFE.search(content):
        raise ValidationError("Dit SVG-bestand bevat scripts. Exporteer het logo opnieuw als gewone SVG of als PNG.")


CYQL_WIDGET_KEYS = ["e", "i", "l", "h", "v", "cr", "m"]
CYQL_WIDGET_CALL = re.compile(r"\}\)\(\s*document\s*,(?P<args>[^)]*)\)")
CYQL_WIDGET_VALUE = re.compile(r"^[A-Za-z0-9_.%-]{1,80}$")


def parse_cyql_widget(code):
    """Haalt de instellingen uit de widgetcode van Cyql (de waarden na `document`).

    We voeren de geplakte code nooit zelf uit: de website bouwt het adres van het
    Cyql-script opnieuw op uit deze waarden. Zo kan er geen ander script binnensluipen.
    """
    match = CYQL_WIDGET_CALL.search(code or "")
    if not match or "dashboard.cyql.app/widgets/cw.js" not in code:
        raise ValidationError("Dit lijkt geen widgetcode van Cyql. Kopieer de volledige code uit het Cyql-dashboard.")
    values = re.findall(r"""['"]([^'"]*)['"]""", match.group("args"))
    if len(values) != len(CYQL_WIDGET_KEYS) or not all(CYQL_WIDGET_VALUE.match(value) for value in values):
        raise ValidationError("De widgetcode heeft niet de verwachte vorm. Kopieer de code opnieuw uit het Cyql-dashboard.")
    return dict(zip(CYQL_WIDGET_KEYS, values))


def parse_emails(text):
    return {line.strip().lower() for line in text.replace(",", "\n").splitlines() if line.strip()}


@register_setting(icon="image", order=10)
class Huisstijl(BaseGenericSetting):
    primary_color = models.CharField(
        "basiskleur",
        max_length=7,
        default="#231F20",
        validators=[hex_validator],
        help_text="Strook met logo en menu bovenaan, voettekst en titels. De tekstkleur erop (wit of zwart) "
        "wordt automatisch gekozen.",
    )
    accent_color = models.CharField(
        "accentkleur",
        max_length=7,
        default="#FF5200",
        validators=[hex_validator],
        help_text="Knoppen en markeringen. Voor tekstlinks wordt automatisch een leesbare tint berekend.",
    )
    logo = models.FileField(
        "logo",
        upload_to="huisstijl/",
        blank=True,
        validators=[FileExtensionValidator(["svg", "png", "webp"]), validate_logo],
        help_text="SVG of PNG met transparante achtergrond. Het staat bovenaan op de basiskleur, op de website en in "
        "de stock-app; kies dus een versie die daarop goed leesbaar is. Leeg: het standaardlogo.",
    )

    panels = [FieldPanel("primary_color"), FieldPanel("accent_color"), FieldPanel("logo")]

    class Meta:
        verbose_name = "huisstijl"

    def clean(self):
        super().clean()
        errors = {}
        if colors.HEX_RE.match(self.accent_color or ""):
            on_accent = colors.readable_on(self.accent_color)
            if colors.contrast(self.accent_color, on_accent) < 3:
                errors["accent_color"] = "Op deze kleur is geen enkele tekstkleur goed leesbaar. Kies een andere."
        if errors:
            raise ValidationError(errors)

    @property
    def on_primary(self):
        """Wit als dat leesbaar is op de basiskleur (4,5:1), anders zwart."""
        return "#FFFFFF" if colors.contrast(self.primary_color, "#FFFFFF") >= 4.5 else "#1A1A1A"

    @property
    def logo_url(self):
        if self.logo:
            return self.logo.url
        from django.templatetags.static import static

        # Het standaardlogo bestaat in een donkere en een lichte versie.
        return static("img/logo.svg" if self.on_primary != "#FFFFFF" else "img/logo-light.svg")

    @property
    def css_variables(self):
        accent_text = colors.darken_until(self.accent_color)
        return {
            "--primary": self.primary_color,
            "--on-primary": self.on_primary,
            "--primary-text": colors.darken_until(self.primary_color),
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
    mail_copy_to = models.EmailField(
        "kopie van klantmails naar", blank=True,
        help_text="Krijgt een kopie van de bevestigingsmails (zie menu E-mails). Leeg: het e-mailadres hierboven.",
    )
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
            [FieldPanel("iban"), FieldPanel("email"), FieldPanel("mail_copy_to"), FieldPanel("phone"),
             FieldPanel("meeting_place")],
            heading="Contact",
        ),
        MultiFieldPanel(
            [FieldPanel("facebook_url"), FieldPanel("strava_url"), FieldPanel("privacy_url")],
            heading="Links",
        ),
    ]

    class Meta:
        verbose_name = "clubgegevens"

    def copy_addresses(self, exclude=()):
        """Het adres voor een kopie van de bevestigingsmails: 'kopie van klantmails naar', anders het clubadres."""
        address = (self.mail_copy_to or self.email or "").strip()
        skip = {a.strip().lower() for a in exclude if a}
        if address and address.lower() not in skip:
            return [address]
        return []


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

    widget_code = models.TextField(
        "widgetcode",
        blank=True,
        help_text="Plak hier de widgetcode uit het Cyql-dashboard (begint met &lt;script&gt;). De widget komt "
        "onderaan de pagina Cyql-app en laadt pas als een bezoeker op de knop tikt. Leeg: geen widget.",
    )
    member_group = models.EmailField(
        "adres ledengroep",
        blank=True,
        help_text="E-mailadres van de Microsoft 365-groep (bv. leden@wtczonnebeke.be). Na elke nachtelijke sync "
        "zet de website alle goedgekeurde Cyql-leden als gast in die groep en haalt ze wie niet meer actief is "
        "eruit. Gebruikers van de tenant in de groep blijven altijd staan. Leeg: de groep wordt niet bijgehouden.",
    )
    member_group_test = models.TextField(
        "enkel deze adressen (test)",
        blank=True,
        help_text="Eén e-mailadres per regel. Ingevuld: de groep bevat enkel deze adressen in plaats van alle "
        "leden. Handig om eerst met een paar adressen te testen; maak leeg om alle leden op te nemen.",
    )

    sync_news = models.BooleanField(
        "synchroniseer nieuws",
        default=False,
        help_text="Aangevinkt: bij elke Cyql-sync leest de website ook de actieve nieuwsberichten uit de app. "
        "Een nieuw bericht wordt na de sync gemaild naar het adres van de ledengroep, met de titel als onderwerp "
        "en de beschrijving als tekst. De eerste keer worden de bestaande berichten enkel onthouden, niet gemaild.",
    )

    panels = [
        HelpPanel(content="<p>De API-sleutel staat niet hier maar in Portainer als <code>CYQL_API_KEY</code>.</p>"),
        FieldPanel("sync_time"),
        FieldPanel("invite_link"),
        FieldPanel("event_url"),
        FieldPanel("widget_code"),
        MultiFieldPanel(
            [FieldPanel("member_group"), FieldPanel("member_group_test"), FieldPanel("sync_news")], heading="Ledengroep"
        ),
    ]

    class Meta:
        verbose_name = "Cyql-instellingen"

    def clean(self):
        super().clean()
        if self.widget_code.strip():
            try:
                parse_cyql_widget(self.widget_code)
            except ValidationError as exc:
                raise ValidationError({"widget_code": exc.messages}) from exc

    @property
    def widget(self):
        """{"element": id, "src": adres van het Cyql-script} of None."""
        if not self.widget_code.strip():
            return None
        try:
            values = parse_cyql_widget(self.widget_code)
        except ValidationError:
            return None
        from urllib.parse import urlencode

        return {"element": values["e"], "src": f"https://dashboard.cyql.app/widgets/cw.js?{urlencode(values)}"}

    @property
    def member_group_test_emails(self):
        return sorted({line.strip().lower() for line in self.member_group_test.splitlines() if "@" in line})

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

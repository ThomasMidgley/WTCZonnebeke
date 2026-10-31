from django import forms
from django.core.mail import EmailMessage
from django.db import models
from django.utils import timezone
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.forms.models import AbstractEmailForm, AbstractFormField
from wagtail.contrib.forms.panels import FormSubmissionsPanel
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Orderable, Page

from .blocks import RICH_FEATURES, BodyBlock


class BasePage(Page):
    intro = models.TextField("inleiding", blank=True, help_text="Korte tekst bovenaan de pagina.")
    body = StreamField(BodyBlock(), verbose_name="inhoud", blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("body")]

    class Meta:
        abstract = True


class HomePage(Page):
    hero_title = models.CharField("titel", max_length=120, default="Samen uit, samen thuis")
    hero_text = models.TextField("ondertitel", blank=True)
    hero_image = models.ForeignKey(
        "wagtailimages.Image", verbose_name="foto", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    hero_button_label = models.CharField("tekst op de knop", max_length=60, blank=True)
    hero_button_page = models.ForeignKey(
        "wagtailcore.Page", verbose_name="knop verwijst naar", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    body = StreamField(BodyBlock(), verbose_name="inhoud", blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("hero_title"),
                FieldPanel("hero_text"),
                FieldPanel("hero_image"),
                FieldRowPanel([FieldPanel("hero_button_label"), FieldPanel("hero_button_page")]),
            ],
            heading="Bovenaan",
        ),
        FieldPanel("body"),
    ]

    parent_page_types = ["wagtailcore.Page"]
    max_count = 1

    class Meta:
        verbose_name = "home"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["events"] = (
            EventPage.objects.live().public().filter(event_date__gte=timezone.localdate()).order_by("event_date")[:3]
        )
        return context


class ContentPage(BasePage):
    parent_page_types = ["pages.HomePage", "pages.ContentPage"]

    class Meta:
        verbose_name = "inhoudspagina"


class BoardPage(BasePage):
    parent_page_types = ["pages.HomePage"]
    max_count = 1

    content_panels = BasePage.content_panels + [InlinePanel("members", label="bestuursleden")]

    class Meta:
        verbose_name = "bestuur"


class BoardMember(Orderable):
    page = ParentalKey(BoardPage, on_delete=models.CASCADE, related_name="members")
    name = models.CharField("naam", max_length=120)
    role = models.CharField("functie", max_length=120)
    tasks = models.TextField("taken", blank=True, help_text="Eén taak per regel.")

    panels = [FieldPanel("name"), FieldPanel("role"), FieldPanel("tasks")]

    @property
    def task_list(self):
        return [line.strip() for line in self.tasks.splitlines() if line.strip()]


class RulesPage(Page):
    intro = models.TextField("inleiding", blank=True)
    version = models.CharField("versie", max_length=80, blank=True, help_text="Bijvoorbeeld: januari 2026.")
    body = RichTextField("reglement", features=RICH_FEATURES, blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("version"), FieldPanel("body")]
    parent_page_types = ["pages.HomePage"]
    max_count = 1

    class Meta:
        verbose_name = "clubreglement"


class EventIndexPage(BasePage):
    parent_page_types = ["pages.HomePage"]
    subpage_types = ["pages.EventPage"]
    max_count = 1

    class Meta:
        verbose_name = "evenementenoverzicht"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["events"] = EventPage.objects.child_of(self).live().public().order_by("event_date")
        return context


class EventPage(BasePage):
    summary = models.CharField("korte omschrijving", max_length=200, blank=True)
    event_date = models.DateField("datum", null=True, blank=True)
    start_place = models.CharField("vertrekplaats", max_length=200, blank=True)
    distances = models.CharField("afstanden", max_length=200, blank=True)
    image = models.ForeignKey(
        "wagtailimages.Image", verbose_name="foto", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    video_url = models.URLField("YouTube-film", blank=True)
    registration_url = models.URLField(
        "link inschrijven", blank=True, help_text="Later: de inschrijving in de webshop."
    )

    content_panels = Page.content_panels + [
        FieldPanel("summary"),
        MultiFieldPanel(
            [FieldPanel("event_date"), FieldPanel("start_place"), FieldPanel("distances")], heading="Praktisch"
        ),
        FieldPanel("image"),
        FieldPanel("intro"),
        FieldPanel("body"),
        FieldPanel("video_url"),
        FieldPanel("registration_url"),
    ]
    parent_page_types = ["pages.EventIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "evenement"


class CyqlPage(BasePage):
    parent_page_types = ["pages.HomePage"]
    max_count = 1

    class Meta:
        verbose_name = "Cyql-app"


class CalendarPage(BasePage):
    """Clubkalender: komende ritten en activiteiten, elke nacht uit Cyql gehaald."""

    parent_page_types = ["pages.HomePage"]
    max_count = 1

    class Meta:
        verbose_name = "clubkalender"

    def get_context(self, request, *args, **kwargs):
        from apps.cyql.models import ClubEvent, Ride, SyncRun

        context = super().get_context(request, *args, **kwargs)
        now = timezone.now()
        items = [{"kind": "rit", "obj": ride} for ride in Ride.objects.filter(start_time__gte=now)]
        items += [{"kind": "activiteit", "obj": event} for event in ClubEvent.objects.filter(start_time__gte=now)]
        items.sort(key=lambda item: item["obj"].start_time)
        months = []
        for item in items:
            month = timezone.localtime(item["obj"].start_time).replace(day=1).date()
            if not months or months[-1]["month"] != month:
                months.append({"month": month, "items": []})
            months[-1]["items"].append(item)
        context["months"] = months
        context["last_sync"] = SyncRun.objects.filter(ok=True).first()
        return context


class RankingPage(BasePage):
    """Klassementen uit Cyql. Welke getoond worden, kies je bij Cyql > Klassementen."""

    show_full_names = models.BooleanField(
        "volledige namen tonen",
        default=False,
        help_text="Standaard tonen we voornaam en initiaal (bv. Jan P.): de pagina is voor iedereen zichtbaar.",
    )

    content_panels = BasePage.content_panels + [FieldPanel("show_full_names")]

    parent_page_types = ["pages.HomePage"]
    max_count = 1

    class Meta:
        verbose_name = "klassement"

    def get_context(self, request, *args, **kwargs):
        from apps.cyql.models import Challenge

        context = super().get_context(request, *args, **kwargs)
        context["challenges"] = Challenge.objects.filter(is_active=True, show_on_site=True).prefetch_related("scores")
        return context


class ContactFormField(AbstractFormField):
    page = ParentalKey("ContactPage", on_delete=models.CASCADE, related_name="form_fields")


class ContactPage(AbstractEmailForm):
    intro = models.TextField("inleiding", blank=True)
    thank_you_text = models.TextField("bedankt-tekst", default="Bedankt voor je bericht. We antwoorden zo snel mogelijk.")

    content_panels = AbstractEmailForm.content_panels + [
        FormSubmissionsPanel(),
        FieldPanel("intro"),
        InlinePanel("form_fields", label="velden"),
        FieldPanel("thank_you_text"),
        MultiFieldPanel(
            [FieldRowPanel([FieldPanel("from_address"), FieldPanel("to_address")]), FieldPanel("subject")],
            heading="E-mail naar het bestuur",
        ),
    ]
    parent_page_types = ["pages.HomePage"]
    max_count = 1

    class Meta:
        verbose_name = "contact"

    def serve(self, request, *args, **kwargs):
        # Honeypot tegen spam: een verborgen veld dat mensen niet invullen.
        if request.method == "POST" and request.POST.get("website"):
            return self.render_landing_page(request, None, *args, **kwargs)
        return super().serve(request, *args, **kwargs)

    def send_mail(self, form):
        # Antwoorden gaan rechtstreeks naar de afzender van het formulier.
        reply_to = [value for name, value in form.cleaned_data.items() if isinstance(form.fields[name], forms.EmailField) and value]
        EmailMessage(
            subject=self.subject or f"Contactformulier {self.title}",
            body=self.render_email(form),
            from_email=self.from_address or None,
            to=[address.strip() for address in self.to_address.split(",") if address.strip()],
            reply_to=reply_to[:1],
        ).send(fail_silently=True)  # het bericht staat sowieso bij Formulieren in de beheeromgeving

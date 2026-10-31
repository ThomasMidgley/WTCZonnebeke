"""Webshop: artikelen met maten, pakketten, bestellingen en stock.

Stock per variant (artikel + heren/dames + maat):
- `stock` is wat fysiek in de kast ligt. Het daalt pas als de stockbeheerder
  een bestelling als geleverd aanduidt.
- gereserveerd is wat in open bestellingen zit: betaald maar nog niet geleverd,
  of aan het afrekenen (30 minuten).
- beschikbaar = stock - gereserveerd. Onder nul is een voorbestelling.
"""

import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.fields import StreamField
from wagtail.models import Orderable, Page

from apps.pages.blocks import BodyBlock

HOLD_MINUTES = 30
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]


class Product(ClusterableModel):
    KIND_ARTICLE = "artikel"
    KIND_PACKAGE = "pakket"
    KIND_EVENT = "event"
    KIND_MEMBERSHIP = "lidgeld"
    KINDS = [
        (KIND_ARTICLE, "Artikel"),
        (KIND_PACKAGE, "Pakket (bundel van artikelen)"),
        (KIND_EVENT, "Event of inschrijving (geen stock, bv. clubfeest)"),
        (KIND_MEMBERSHIP, "Lidgeld (een aansluiting per persoon)"),
    ]
    # Titels van de rubrieken in de shop, in deze volgorde.
    CATEGORIES = [
        (KIND_MEMBERSHIP, "Lidgeld"), (KIND_ARTICLE, "Artikels"), (KIND_PACKAGE, "Pakketten"), (KIND_EVENT, "Events"),
    ]

    title = models.CharField("naam", max_length=120)
    slug = models.SlugField("adres", unique=True, help_text="Deel van het webadres, bv. trui-korte-mouw.")
    kind = models.CharField("soort", max_length=10, choices=KINDS, default=KIND_ARTICLE)
    description = models.TextField("beschrijving", blank=True)
    image = models.ForeignKey(
        "wagtailimages.Image", verbose_name="foto", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    price = models.DecimalField("prijs (€)", max_digits=7, decimal_places=2)
    members_only = models.BooleanField(
        "enkel voor leden", default=True, help_text="Controle op het e-mailadres in de ledenlijst van Cyql."
    )
    is_visible = models.BooleanField("zichtbaar in de shop", default=True)
    sort_order = models.PositiveIntegerField("volgorde", default=0)

    # Enkel voor events en inschrijvingen
    max_places = models.PositiveIntegerField(
        "maximum aantal plaatsen", null=True, blank=True, help_text="Leeg: onbeperkt. Daarna staat het event op volzet."
    )
    price_after = models.DecimalField(
        "prijs vanaf datum (€)", max_digits=7, decimal_places=2, null=True, blank=True,
        help_text="Bv. lidgeld €75 vanaf 1 december. Leeg: altijd dezelfde prijs.",
    )
    price_after_date = models.DateField("vanaf", null=True, blank=True)
    closes_at = models.DateTimeField("inschrijven kan tot", null=True, blank=True, help_text="Leeg: geen einddatum.")
    form = models.ForeignKey(
        "formulieren.Form", verbose_name="extra vragen", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", help_text="Een formulier uit het menu Formulieren. De vragen komen bij de inschrijving.",
    )
    confirmation_text = models.TextField(
        "extra tekst in de bevestiging", blank=True,
        help_text="Komt in de bevestigingsmail van wie dit kocht, bv. het uur en de zaal van het clubfeest.",
    )
    requires_main = models.BooleanField(
        "enkel samen met een 1e aansluiting", default=False,
        help_text="Enkel voor lidgeld, bv. 2e aansluiting of gezinsaansluiting: kan enkel als er ook een "
        "aansluiting zonder dit vinkje in het winkelmandje zit.",
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("title"), FieldPanel("slug"), FieldPanel("kind"), FieldPanel("price"), FieldPanel("image")],
            heading="Artikel",
        ),
        FieldPanel("description"),
        FieldRowPanel([FieldPanel("members_only"), FieldPanel("is_visible"), FieldPanel("sort_order")]),
        MultiFieldPanel(
            [
                FieldRowPanel([FieldPanel("max_places"), FieldPanel("closes_at")]),
                FieldRowPanel([FieldPanel("price_after"), FieldPanel("price_after_date")]),
                FieldPanel("form"),
                FieldPanel("confirmation_text"),
                FieldPanel("requires_main"),
            ],
            heading="Enkel voor events en lidgeld",
        ),
        InlinePanel(
            "variants",
            heading="Maten en stock",
            label="maat",
            help_text="Enkel voor een artikel. Een pakket gebruikt de maten van zijn onderdelen.",
        ),
        InlinePanel("components", heading="Onderdelen (enkel voor een pakket)", label="onderdeel"),
    ]

    class Meta:
        ordering = ["sort_order", "title"]
        verbose_name = "artikel"
        verbose_name_plural = "artikels"

    def __str__(self):
        return self.title

    @property
    def is_package(self):
        return self.kind == self.KIND_PACKAGE

    @property
    def is_event(self):
        return self.kind == self.KIND_EVENT

    @property
    def is_membership(self):
        """Lidgeld: per persoon één aansluiting. Na betaling volgt de uitnodigingslink voor Cyql."""
        return self.kind == self.KIND_MEMBERSHIP

    @property
    def is_registration(self):
        """Events en lidgeld: geen maten of stock, wel eventueel extra vragen, een einddatum en een prijsverhoging."""
        return self.kind in (self.KIND_EVENT, self.KIND_MEMBERSHIP)

    def participants_link(self):
        if not self.is_event:
            return ""
        from django.urls import reverse
        from django.utils.html import format_html

        return format_html('<a href="{}">{} ingeschreven</a>', reverse("shop_participants", args=[self.pk]), self.places_taken)

    participants_link.short_description = "deelnemers"

    def current_price(self, today=None):
        today = today or timezone.localdate()
        if self.price_after is not None and self.price_after_date and today >= self.price_after_date:
            return self.price_after
        return self.price

    @property
    def places_taken(self):
        """Ingeschreven (betaald) of nog aan het afrekenen."""
        lines = OrderLine.objects.filter(product=self, package__isnull=True)
        taken = lines.reserving() | lines.filter(order__status=Order.DELIVERED)
        return taken.aggregate(n=Sum("quantity"))["n"] or 0

    @property
    def places_left(self):
        if self.max_places is None:
            return None
        return max(self.max_places - self.places_taken, 0)

    @property
    def is_full(self):
        return self.max_places is not None and self.places_left <= 0

    @property
    def is_closed(self):
        return self.closes_at is not None and self.closes_at <= timezone.now()

    def visible_variants(self):
        return [v for v in self.variants.all() if v.is_active]


class Variant(Orderable):
    GENDERS = [("", "Unisex"), ("H", "Heren"), ("D", "Dames")]

    product = ParentalKey(Product, on_delete=models.CASCADE, related_name="variants")
    gender = models.CharField("heren/dames", max_length=1, choices=GENDERS, blank=True)
    size = models.CharField("maat", max_length=10)
    article_number = models.CharField("artikelnummer", max_length=30, blank=True)
    stock = models.IntegerField("in de kast", default=0, help_text="Wijzig je dit hier, dan komt dat niet in het logboek.")
    is_active = models.BooleanField("te koop", default=True)

    panels = [
        FieldRowPanel([FieldPanel("gender"), FieldPanel("size"), FieldPanel("article_number")]),
        FieldRowPanel([FieldPanel("stock"), FieldPanel("is_active")]),
    ]

    class Meta(Orderable.Meta):
        verbose_name = "maat"
        verbose_name_plural = "maten"

    def __str__(self):
        return f"{self.product.title} {self.label}"

    @property
    def label(self):
        gender = dict(self.GENDERS).get(self.gender, "")
        return f"{gender} {self.size}".strip() if self.gender else self.size

    @property
    def reserved(self):
        return OrderLine.objects.reserving().filter(variant=self).aggregate(n=Sum("quantity"))["n"] or 0

    @property
    def available(self):
        return self.stock - self.reserved


class PackageComponent(Orderable):
    package = ParentalKey(Product, on_delete=models.CASCADE, related_name="components")
    component = models.ForeignKey(
        Product,
        verbose_name="artikel",
        on_delete=models.PROTECT,
        related_name="+",
        limit_choices_to={"kind": Product.KIND_ARTICLE},
    )

    panels = [FieldPanel("component")]

    class Meta(Orderable.Meta):
        verbose_name = "onderdeel"
        verbose_name_plural = "onderdelen"


def new_token():
    return secrets.token_urlsafe(16)


class Order(models.Model):
    PENDING = "afrekenen"
    PAID = "betaald"
    READY = "klaar"
    DELIVERED = "geleverd"
    NOT_COLLECTED = "niet_afgehaald"
    CANCELLED = "geannuleerd"
    EXPIRED = "verlopen"
    STATUSES = [
        (PENDING, "Aan het afrekenen"),
        (PAID, "Betaald"),
        (READY, "Ligt klaar"),
        (DELIVERED, "Geleverd"),
        (NOT_COLLECTED, "Niet afgehaald (terug in voorraad)"),
        (CANCELLED, "Geannuleerd"),
        (EXPIRED, "Verlopen"),
    ]
    OPEN = (PAID, READY)

    number = models.CharField("nummer", max_length=20, unique=True, editable=False)
    token = models.CharField(max_length=32, unique=True, default=new_token, editable=False)
    status = models.CharField("status", max_length=20, choices=STATUSES, default=PENDING)
    name = models.CharField("naam", max_length=120)
    email = models.EmailField("e-mailadres")
    phone = models.CharField("gsm", max_length=20, blank=True)
    note = models.TextField("opmerking", blank=True)
    total = models.DecimalField("totaal (€)", max_digits=8, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField("besteld op", auto_now_add=True)
    expires_at = models.DateTimeField("afrekenen tot", null=True, blank=True)
    paid_at = models.DateTimeField("betaald op", null=True, blank=True)
    ready_at = models.DateTimeField("klaar gemeld op", null=True, blank=True)
    delivered_at = models.DateTimeField("geleverd op", null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="behandeld door", null=True, blank=True, on_delete=models.SET_NULL
    )
    stripe_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "bestelling"
        verbose_name_plural = "bestellingen"

    def __str__(self):
        return f"{self.number} {self.name}"

    def save(self, *args, **kwargs):
        if not self.number:
            year = timezone.localdate().year
            count = Order.objects.filter(number__startswith=f"{year}-").count() + 1
            self.number = f"{year}-{count:04d}"
            while Order.objects.filter(number=self.number).exists():
                count += 1
                self.number = f"{year}-{count:04d}"
        if self.status == self.PENDING and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=HOLD_MINUTES)
        super().save(*args, **kwargs)

    @property
    def has_goods(self):
        """Zit er kledij in (iets om af te halen), of enkel inschrijvingen?"""
        return any(line.variant_id for line in self.lines.all())

    @property
    def has_preorder(self):
        return any(line.is_preorder for line in self.lines.all())

    @property
    def can_mark_not_collected(self):
        """Volgens het clubreglement: 4 weken na de melding dat de bestelling klaarligt."""
        return self.status == self.READY and self.ready_at and timezone.now() - self.ready_at >= timedelta(weeks=4)


class OrderLineQuerySet(models.QuerySet):
    def reserving(self, now=None):
        """Lijnen die stock vasthouden: betaald en niet geleverd, of nog aan het afrekenen."""
        now = now or timezone.now()
        return self.filter(
            Q(order__status__in=Order.OPEN) | Q(order__status=Order.PENDING, order__expires_at__gt=now)
        )


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    variant = models.ForeignKey(Variant, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    package = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Deel van dit pakket."
    )
    title = models.CharField("artikel", max_length=200)
    size = models.CharField("maat", max_length=30, blank=True)
    quantity = models.PositiveIntegerField("aantal", default=1)
    unit_price = models.DecimalField("prijs per stuk (€)", max_digits=7, decimal_places=2)
    is_preorder = models.BooleanField("voorbestelling", default=False)
    answers = models.JSONField("antwoorden", default=list, blank=True, help_text="Extra vragen bij een inschrijving.")

    objects = OrderLineQuerySet.as_manager()

    class Meta:
        ordering = ["id"]

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class StockMovement(models.Model):
    """Logboek: elke wijziging van de stock, met wie, wanneer en waarom."""

    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="movements")
    delta = models.IntegerField("wijziging")
    stock_after = models.IntegerField("stock daarna")
    reason = models.CharField("reden", max_length=200)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="door", null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField("op", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "stockwijziging"
        verbose_name_plural = "logboek stock"

    def __str__(self):
        return f"{self.variant} {self.delta:+d}"


class ShopPage(RoutablePageMixin, Page):
    """De webshop: /shop/ toont de artikels, /shop/<artikel>/ het artikel met maatkeuze."""

    intro = models.TextField("inleiding", blank=True)
    body = StreamField(BodyBlock(), verbose_name="inhoud onder de artikels", blank=True)
    preorder_text = models.TextField(
        "uitleg voorbestelling",
        default="Niet op voorraad? Je kunt toch bestellen. We groeperen de bestellingen bij Bioracer; "
        "reken op enkele weken levertijd. We laten je weten wanneer je bestelling klaarligt.",
    )

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("preorder_text"), FieldPanel("body")]
    parent_page_types = ["pages.HomePage"]
    subpage_types = []
    max_count = 1

    class Meta:
        verbose_name = "webshop"

    @path("")
    def index(self, request):
        products = list(Product.objects.filter(is_visible=True).select_related("image"))
        categories = [
            {"kind": kind, "title": title, "products": [p for p in products if p.kind == kind]}
            for kind, title in Product.CATEGORIES
        ]
        categories = [c for c in categories if c["products"]]
        return self.render(request, context_overrides={"products": products, "categories": categories})

    @path("<slug:slug>/")
    def product(self, request, slug):
        from django.contrib import messages
        from django.shortcuts import get_object_or_404, redirect

        from .forms import AddToCartForm
        from .services import Cart

        product = get_object_or_404(Product, slug=slug, is_visible=True)
        form = AddToCartForm(product, request.POST or None)
        if request.method == "POST" and form.is_valid():
            Cart(request.session).add(
                product, form.cleaned_data["variants"], form.cleaned_data["qty"], answers=form.answers() or None
            )
            messages.success(request, f"{product.title} zit in je winkelmandje.")
            return redirect("shop_cart")
        return self.render(
            request,
            template="shop/product.html",
            context_overrides={"product": product, "form": form},
        )

"""Startinhoud van de webshop, uit seed/voorraad-kledij.xlsx (stand 30-06-2026).

De stockaantallen zijn voorlopig fictief; de stockbeheerder zet ze juist via de stock-app.
"""

import datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.images import ImageFile
from django.utils import timezone
from wagtail.images import get_image_model

from .models import SIZES, PackageComponent, Product, Variant

SEED_DIR = Path(settings.BASE_DIR) / "seed"
DUMMY_STOCK = {"XS": 0, "S": 2, "M": 3, "L": 3, "XL": 2, "XXL": 1, "XXXL": 0}

# slug, naam, prijs, {geslacht: artikelnummer}, foto, beschrijving
ARTICLES = [
    ("trui-korte-mouw", "Trui korte mouw", "41", {"H": "41361", "D": "41361 D"}, "trui-kort.jpg",
     "Bioracer Icon Classic (heren) of Prof (dames), lange rits."),
    ("trui-lange-mouw", "Trui lange mouw", "68", {"H": "51472", "D": "51472 D"}, None,
     "Bioracer Icon Tempest, lange rits."),
    ("korte-broek-bretellen", "Korte broek met bretellen", "67", {"H": "52147", "D": "52147 D"}, "broek-kort.jpg", ""),
    ("lange-broek", "Lange broek", "86", {"H": "53532", "D": "53532D"}, None, "Met voorgevormde bretellen."),
    ("body", "Body", "59", {"H": "51972", "D": "57972 D"}, None, ""),
    ("kniebroek", "Kniebroek ¾", "86", {"": "54421"}, None, "Bibshort tot over de knie."),
    ("korte-broek-dames", "Korte broek dames zonder bretellen", "59", {"D": "52158 D"}, None, ""),
    ("thermisch-fietshirt", "Thermisch fietshirt", "75", {"H": "51472", "D": "51472 D"}, None, "Bioracer Icon Tempest."),
    ("armstukken", "Armstukken", "19", {"": "59350"}, None, "Voor het tussenseizoen."),
    ("kousen", "Kousen", "16", {"": "59107"}, None, ""),
]

PACKAGE = ("clubpakket", "Clubpakket", "180", [
    "trui-korte-mouw", "trui-lange-mouw", "korte-broek-bretellen", "lange-broek", "body", "kousen",
])


def seed_image(filename, title):
    Image = get_image_model()
    image = Image.objects.filter(title=title).first()
    path = SEED_DIR / filename
    if image or not path.exists():
        return image
    with path.open("rb") as handle:
        return Image.objects.create(title=title, file=ImageFile(handle, name=filename))


def seed_shop():
    """Maakt de artikels enkel aan als de shop nog leeg is."""
    if Product.objects.exists():
        return False
    for order, (slug, title, price, numbers, photo, description) in enumerate(ARTICLES, start=1):
        product = Product.objects.create(
            slug=slug, title=title, price=Decimal(price), description=description,
            image=seed_image(photo, title) if photo else None, sort_order=order * 10,
        )
        position = 0
        for gender, number in numbers.items():
            for size in SIZES:
                Variant.objects.create(
                    product=product, gender=gender, size=size, article_number=number,
                    stock=DUMMY_STOCK[size], sort_order=position,
                )
                position += 1
    slug, title, price, parts = PACKAGE
    package = Product.objects.create(
        slug=slug, title=title, kind=Product.KIND_PACKAGE, price=Decimal(price), sort_order=0,
        description="Het volledige clubpakket: trui korte en lange mouw, korte en lange broek, body en kousen. "
        "Je kiest de maat per onderdeel.",
    )
    for position, part in enumerate(parts):
        PackageComponent.objects.create(package=package, component=Product.objects.get(slug=part), sort_order=position)
    return True


MEMBERSHIP_QUESTIONS = [
    # vraag, soort, verplicht, keuzes, sprong (antwoord, naar vraag nr.)
    ("Geboortedatum", "datum", True, "", None),
    ("Adres (straat, nummer, postcode, gemeente)", "tekst", True, "", None),
    ("In welke groep rijd je meestal?", "keuze", True, "A30+\nB28\nB25\nB22\nWeet ik nog niet", None),
    ("Wil je gezinsleden gratis meeverzekeren?", "keuze", True, "Ja\nNee", ("Nee", 0)),
    ("Naam en geboortedatum van elk gezinslid", "lange_tekst", True, "", None),
]


def seed_membership():
    """Lidgeld met de extra vragen voor nieuwe leden. Enkel aanmaken als er nog geen lidgeld bestaat."""
    from apps.core.models import Clubgegevens
    from apps.formulieren.models import Form, Question

    if Product.objects.filter(is_membership=True).exists() or Product.objects.filter(slug="lidgeld").exists():
        return False
    form = Form.objects.filter(title="Lidgeld").first()
    if form is None:
        form = Form.objects.create(
            title="Lidgeld",
            thanks="Bedankt! Je inschrijving als lid is goed ontvangen.",
            notify_emails=Clubgegevens.load().email or "",
        )
        for position, (label, kind, required, choices, jump) in enumerate(MEMBERSHIP_QUESTIONS):
            Question.objects.create(
                form=form, sort_order=position, label=label, kind=kind, required=required, choices=choices,
                jump_answer=jump[0] if jump else "", jump_to=jump[1] if jump else None,
            )
    today = timezone.localdate()
    Product.objects.create(
        slug="lidgeld", title="Lidgeld", kind=Product.KIND_EVENT, price=Decimal("65"),
        price_after=Decimal("75"), price_after_date=datetime.date(today.year, 12, 1),
        members_only=False, is_membership=True, form=form, sort_order=0,
        description="Lidmaatschap voor het volgende seizoen, met verzekering. Gezinsleden verzeker je gratis mee. "
        "Na 1 december betaal je €10 meer. Wie niet betaald heeft voor 31 december, is uittredend lid.",
    )
    return True

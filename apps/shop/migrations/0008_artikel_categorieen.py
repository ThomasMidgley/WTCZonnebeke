"""Artikels in drie categorieën (Algemeen, Dames, Heren) met één artikelnummer per artikel.

Een artikel met zowel heren- als damesmaten wordt gesplitst: het bestaande artikel
wordt het herenartikel, de damesmaten verhuizen naar een nieuw damesartikel (adres
eindigt op -dames). Stock, logboek en bestellingen blijven bij dezelfde maten. In
een pakket wordt het damesartikel het alternatief voor het herenartikel.
"""

from django.db import migrations, models
import django.db.models.deletion

CATEGORY = {"": "algemeen", "H": "heren", "D": "dames"}
COPY_FIELDS = [
    "kind", "description", "image_id", "price", "members_only", "is_visible", "sort_order", "confirmation_text",
]


def unique_slug(Product, slug):
    candidate, n = slug, 2
    while Product.objects.filter(slug=candidate).exists():
        candidate, n = f"{slug}-{n}", n + 1
    return candidate


def split_articles(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    Variant = apps.get_model("shop", "Variant")
    OrderLine = apps.get_model("shop", "OrderLine")
    PackageComponent = apps.get_model("shop", "PackageComponent")
    for product in Product.objects.filter(kind="artikel"):
        genders = set(Variant.objects.filter(product=product).values_list("gender", flat=True))
        ladies_number = product.article_number_ladies or product.article_number
        if "D" in genders and genders & {"H", ""}:
            ladies = Product.objects.create(
                title=product.title,
                slug=unique_slug(Product, f"{product.slug}-dames"[:50]),
                category="dames",
                article_number=ladies_number,
                **{field: getattr(product, field) for field in COPY_FIELDS},
            )
            moved = list(Variant.objects.filter(product=product, gender="D").values_list("pk", flat=True))
            Variant.objects.filter(pk__in=moved).update(product=ladies)
            OrderLine.objects.filter(product=product, variant_id__in=moved).update(product=ladies)
            PackageComponent.objects.filter(component=product, alternative__isnull=True).update(alternative=ladies)
            product.category = "heren" if "H" in genders else "algemeen"
        elif genders == {"D"}:
            product.category = "dames"
            product.article_number = ladies_number
        elif genders == {"H"}:
            product.category = "heren"
        else:
            product.category = "algemeen"
        product.save(update_fields=["category", "article_number"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0007_artikelnummer_per_artikel")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.CharField(
                choices=[("algemeen", "Algemeen"), ("dames", "Dames"), ("heren", "Heren")], default="algemeen",
                help_text="Enkel voor artikels: de rubriek in de webshop en in het stockbeheer.", max_length=10,
                verbose_name="categorie",
            ),
        ),
        migrations.AddField(
            model_name="packagecomponent",
            name="alternative",
            field=models.ForeignKey(
                blank=True, help_text="Bv. de damesversie van een herenartikel: de koper kiest dan een maat uit beide.",
                limit_choices_to={"kind": "artikel"}, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="+", to="shop.product", verbose_name="of in de plaats",
            ),
        ),
        migrations.RunPython(split_articles, migrations.RunPython.noop),
        migrations.RemoveField(model_name="product", name="article_number_ladies"),
        migrations.RemoveField(model_name="variant", name="gender"),
    ]

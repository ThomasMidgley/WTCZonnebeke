"""Artikels in drie categorieën (Algemeen, Dames, Heren) met één artikelnummer per artikel.

Een artikel met zowel heren- als damesmaten wordt gesplitst: het bestaande artikel
wordt het herenartikel, de damesmaten verhuizen naar een nieuw damesartikel (adres
eindigt op -dames). Stock, logboek en bestellingen blijven bij dezelfde maten. In
Een pakket met gesplitste onderdelen wordt een herenpakket (het bestaande, naam
+ " heren") en een nieuw damespakket met de damesartikels. Het thermisch
fietsshirt (fout in de stocklijst: zelfde nummer als de trui lange mouw) verdwijnt,
of wordt verborgen als er al bestellingen voor zijn.
"""

from django.db import migrations, models

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

    shirt = Product.objects.filter(slug="thermisch-fietshirt").first()
    if shirt and not PackageComponent.objects.filter(component=shirt).exists():
        if OrderLine.objects.filter(product=shirt).exists():
            shirt.is_visible = False
            shirt.save(update_fields=["is_visible"])
        else:
            shirt.delete()

    ladies_version = {}
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
            ladies_version[product.pk] = ladies
            product.category = "heren" if "H" in genders else "algemeen"
        elif genders == {"D"}:
            product.category = "dames"
            product.article_number = ladies_number
        elif genders == {"H"}:
            product.category = "heren"
        else:
            product.category = "algemeen"
        product.save(update_fields=["category", "article_number"])

    for package in Product.objects.filter(kind="pakket"):
        components = list(PackageComponent.objects.filter(package=package).order_by("sort_order", "id"))
        if not any(c.component_id in ladies_version for c in components):
            continue
        ladies_package = Product.objects.create(
            title=f"{package.title} dames",
            slug=unique_slug(Product, f"{package.slug}-dames"[:50]),
            **{field: getattr(package, field) for field in COPY_FIELDS},
        )
        for component in components:
            PackageComponent.objects.create(
                package=ladies_package,
                component=ladies_version.get(component.component_id, component.component),
                sort_order=component.sort_order,
            )
        package.title = f"{package.title} heren"
        package.save(update_fields=["title"])


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
        migrations.RunPython(split_articles, migrations.RunPython.noop),
        migrations.RemoveField(model_name="product", name="article_number_ladies"),
        migrations.RemoveField(model_name="variant", name="gender"),
    ]

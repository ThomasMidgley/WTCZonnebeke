from django.db import migrations, models


def copy_numbers(apps, schema_editor):
    """Het eerste nummer van de heren- of unisexmaten wordt het artikelnummer, dat van de damesmaten het damesnummer."""
    Product = apps.get_model("shop", "Product")
    for product in Product.objects.all():
        numbers = {}
        for variant in product.variants.order_by("sort_order", "id"):
            if variant.article_number:
                numbers.setdefault(variant.gender, variant.article_number)
        main = numbers.get("H") or numbers.get("") or numbers.get("D", "")
        ladies = numbers.get("D", "")
        product.article_number = main
        product.article_number_ladies = ladies if ladies != main else ""
        product.save(update_fields=["article_number", "article_number_ladies"])


def copy_back(apps, schema_editor):
    Variant = apps.get_model("shop", "Variant")
    for variant in Variant.objects.select_related("product"):
        product = variant.product
        number = product.article_number_ladies if variant.gender == "D" and product.article_number_ladies else product.article_number
        variant.article_number = number
        variant.save(update_fields=["article_number"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0006_lidgeld_een_vakje")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="article_number",
            field=models.CharField(
                blank=True, help_text="Eén nummer voor alle maten van dit artikel.", max_length=30,
                verbose_name="artikelnummer",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="article_number_ladies",
            field=models.CharField(
                blank=True, help_text="Enkel invullen als de damesmaten een ander nummer hebben (bv. 41361 D).",
                max_length=30, verbose_name="artikelnummer dames",
            ),
        ),
        migrations.RunPython(copy_numbers, copy_back),
        migrations.RemoveField(model_name="variant", name="article_number"),
    ]

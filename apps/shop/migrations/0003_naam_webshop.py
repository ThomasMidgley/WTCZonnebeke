"""De shoppagina heette "Clubkledij"; ze bevat nu ook events en heet voortaan "Webshop"."""

from django.db import migrations


def rename(apps, schema_editor):
    ShopPage = apps.get_model("shop", "ShopPage")
    Revision = apps.get_model("wagtailcore", "Revision")
    for page in ShopPage.objects.filter(title="Clubkledij"):
        page.title = "Webshop"
        page.draft_title = "Webshop"
        page.save(update_fields=["title", "draft_title"])
        revision = Revision.objects.filter(pk=page.latest_revision_id).first()
        if revision and revision.content.get("title") == "Clubkledij":
            revision.content["title"] = "Webshop"
            revision.content["draft_title"] = "Webshop"
            revision.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0002_events_en_inschrijvingen"),
    ]

    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]

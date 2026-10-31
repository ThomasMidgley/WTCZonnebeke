from django.db import migrations


def delete_submissions(apps, schema_editor):
    # Berichten van het contactformulier worden niet meer bewaard; ze staan al in de mailbox van de club.
    apps.get_model("wagtailforms", "FormSubmission").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0003_downloadspage"),
        ("wagtailforms", "0001_initial"),
    ]

    operations = [migrations.RunPython(delete_submissions, migrations.RunPython.noop)]

from django.db import migrations

OLD = "Geregistreerd bij VWB"


def drop_check(apps, schema_editor):
    """Bij het lidgeld volstaat één vakje: 'Betaald aan VWB'."""
    Product = apps.get_model("shop", "Product")
    form_ids = set(Product.objects.filter(kind="lidgeld").exclude(form=None).values_list("form_id", flat=True))
    Form = apps.get_model("formulieren", "Form")
    for form in Form.objects.filter(pk__in=form_ids):
        lines = [line for line in form.admin_checks.splitlines() if line.strip() and line.strip() != OLD]
        form.admin_checks = "\n".join(lines)
        form.save(update_fields=["admin_checks"])
        for submission in form.submissions.all():
            if OLD in (submission.checks or {}):
                submission.checks.pop(OLD)
                submission.save(update_fields=["checks"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0005_product_confirmation_text"),
        ("formulieren", "0003_form_send_confirmation"),
    ]

    operations = [migrations.RunPython(drop_check, migrations.RunPython.noop)]

import csv
import io

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from apps.core.middleware import SecurityHeadersMiddleware

from . import herinschrijving, services
from .forms import PublicForm
from .models import Form

TURNSTILE_CSP = (
    SecurityHeadersMiddleware.PUBLIC_CSP.replace("script-src 'self'", "script-src 'self' https://challenges.cloudflare.com")
    .replace("frame-src ", "frame-src https://challenges.cloudflare.com ")
)


def client_ip(request):
    return request.headers.get("CF-Connecting-IP") or request.META.get("REMOTE_ADDR", "")


@never_cache
def form_view(request, code):
    form_obj = get_object_or_404(Form, code=code)
    if not form_obj.is_open:
        response = render(request, "formulieren/closed.html", {"form_obj": form_obj})
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
    form = PublicForm(form_obj, request.POST or None, remote_ip=client_ip(request))
    if request.method == "POST" and form.is_valid():
        services.save_submission(form_obj, form.answers(), email=form.first_email())
        return redirect("formulier_klaar", code=form_obj.code)
    response = render(
        request,
        "formulieren/form.html",
        {"form_obj": form_obj, "form": form, "turnstile_site_key": settings.TURNSTILE_SITE_KEY},
    )
    response["X-Robots-Tag"] = "noindex, nofollow"
    if settings.TURNSTILE_SITE_KEY:
        response["Content-Security-Policy"] = TURNSTILE_CSP
    return response


def form_done(request, code):
    form_obj = get_object_or_404(Form, code=code)
    response = render(request, "formulieren/done.html", {"form_obj": form_obj})
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


# ---------------------------------------------------------------- beheer


def answers_view(request, pk):
    form_obj = get_object_or_404(Form, pk=pk)
    checks = form_obj.check_labels()
    if request.method == "POST" and checks:
        changed = services.save_checks(form_obj, request.POST)
        messages.success(request, f"{changed} antwoord{'' if changed == 1 else 'en'} bijgewerkt.")
        return redirect("formulier_antwoorden", pk=form_obj.pk)
    header, rows = services.submissions_table(form_obj)
    submissions = list(form_obj.submissions.all().order_by("created_at"))
    # Rijen met per afvinkvakje (naam van het vakje, aangevinkt?) voor de lijst.
    table = []
    for submission, row in zip(submissions, rows):
        boxes = [
            (f"check-{submission.pk}-{index}", label, bool(submission.checks.get(label)))
            for index, label in enumerate(checks)
        ]
        table.append({"cells": row[: len(row) - len(checks)], "boxes": boxes})
    return render(
        request,
        "formulieren/admin_answers.html",
        {"form_obj": form_obj, "header": header[: len(header) - len(checks)], "checks": checks, "table": table},
    )


def answers_clear(request, pk):
    """Alle antwoorden van een formulier wissen, zodat het formulier opnieuw gebruikt kan worden."""
    form_obj = get_object_or_404(Form, pk=pk)
    count = form_obj.submissions.count()
    if request.method == "POST":
        form_obj.submissions.all().delete()
        messages.success(request, f"{count} antwoord{'' if count == 1 else 'en'} gewist.")
        return redirect("formulier_antwoorden", pk=form_obj.pk)
    return render(request, "formulieren/admin_clear.html", {"form_obj": form_obj, "count": count})


def membership_compare(request, pk):
    """Herinschrijving: de lijst vergelijken met de leden in Cyql."""
    from apps.cyql.models import SyncRun

    form_obj = get_object_or_404(Form, pk=pk)
    both, only_list, only_cyql = herinschrijving.compare(form_obj)
    last_sync = SyncRun.objects.filter(ok=True).first()
    return render(
        request,
        "formulieren/admin_cyql.html",
        {"form_obj": form_obj, "both": both, "only_list": only_list, "only_cyql": only_cyql, "last_sync": last_sync},
    )


IMPORT_HEADER = ["Voornaam", "Naam", "E-mail"]


def membership_import_csv(request, pk):
    """Csv om in Cyql te importeren: wie in de lijst staat maar nog geen lid is in Cyql."""
    form_obj = get_object_or_404(Form, pk=pk)
    _, only_list, _ = herinschrijving.compare(form_obj)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(IMPORT_HEADER)
    for person in only_list:
        writer.writerow([person.first_name, person.last_name, person.email])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="import-cyql.csv"'
    return response


def membership_inactive_export(request, pk):
    """Excel met wie in Cyql staat maar zich niet heringeschreven heeft."""
    form_obj = get_object_or_404(Form, pk=pk)
    _, _, only_cyql = herinschrijving.compare(form_obj)
    rows = [[m.first_name, m.last_name, m.email] for m in only_cyql]
    content = services.xlsx_response_bytes("Inactieve leden", ["Voornaam", "Naam", "E-mail"], rows)
    return xlsx_response(content, "inactieve leden")


def answers_export(request, pk):
    form_obj = get_object_or_404(Form, pk=pk)
    header, rows = services.submissions_table(form_obj)
    content = services.xlsx_response_bytes(form_obj.title, header, rows)
    return xlsx_response(content, form_obj.title)


def xlsx_response(content, title):
    if not content:
        raise Http404
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{slugify(title) or "export"}.xlsx"'
    return response

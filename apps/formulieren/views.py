from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from apps.core.middleware import SecurityHeadersMiddleware

from . import services
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

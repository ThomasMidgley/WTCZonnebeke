"""Beheer van de automatische mails: overzicht, teksten aanpassen, voorbeeld, testmail en logboek."""

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import Clubgegevens

from . import services
from .models import MailLog, MailTemplate
from .registry import CONTACT_INFO, MAILS, sample_context


def superuser_only(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


class MailTemplateForm(forms.ModelForm):
    class Meta:
        model = MailTemplate
        fields = ["subject", "intro", "outro", "enabled", "copy_to_club"]
        widgets = {"intro": forms.Textarea(attrs={"rows": 6}), "outro": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, spec, **kwargs):
        super().__init__(*args, **kwargs)
        if not spec.can_copy:
            del self.fields["copy_to_club"]


@superuser_only
def index(request):
    rows = [{"spec": spec, "template": MailTemplate.get(key)} for key, spec in MAILS.items()]
    failed = MailLog.objects.filter(ok=False).count()
    return render(request, "mails/index.html", {
        "rows": rows, "contact": CONTACT_INFO, "copy_address": next(iter(Clubgegevens.load().copy_addresses()), ""),
        "failed": failed,
    })


@superuser_only
def edit(request, key):
    spec = MAILS.get(key)
    if spec is None:
        raise Http404
    template = MailTemplate.get(key)
    action = request.POST.get("action", "")
    if action == "reset":
        template.reset()
        messages.success(request, "De standaardtekst staat terug.")
        return redirect("mails_edit", key=key)
    form = MailTemplateForm(request.POST or None, instance=template, spec=spec)
    preview = None
    if request.method == "POST" and form.is_valid():
        draft = form.save(commit=False)  # nog niet opgeslagen: voor voorbeeld en testmail
        if action == "save":
            draft.save()
            messages.success(request, f"'{spec.label}' is opgeslagen.")
            return redirect("mails_edit", key=key)
        subject, body = services.render(key, sample_context(spec), draft)
        if action == "test":
            if not request.user.email:
                messages.error(request, "Je account heeft geen e-mailadres.")
            else:
                try:
                    EmailMessage(f"[TEST] {subject}", body, to=[request.user.email]).send()
                    messages.success(request, f"Testmail verstuurd naar {request.user.email}. Nog niet opgeslagen.")
                except Exception as exc:
                    messages.error(request, f"Testmail mislukt: {exc}")
        preview = {"subject": subject, "body": body}
    elif request.method == "GET":
        subject, body = services.render(key, sample_context(spec))
        preview = {"subject": subject, "body": body}
    return render(request, "mails/edit.html", {"spec": spec, "form": form, "preview": preview})


@superuser_only
def log(request):
    entries = MailLog.objects.all()
    if request.GET.get("mislukt"):
        entries = entries.filter(ok=False)
    page = Paginator(entries, 100).get_page(request.GET.get("p"))
    labels = {key: spec.label for key, spec in MAILS.items()}
    labels["contact"] = CONTACT_INFO["label"]
    for entry in page:
        entry.label = labels.get(entry.key, entry.key)
        entry.can_resend = entry.key in MAILS and entry.object_id
    return render(request, "mails/log.html", {"page": page, "only_failed": bool(request.GET.get("mislukt"))})


@superuser_only
@require_POST
def resend(request, pk):
    entry = get_object_or_404(MailLog, pk=pk)
    spec = MAILS.get(entry.key)
    if spec is None or not entry.object_id:
        raise Http404
    if spec.kind == "order":
        from apps.shop.models import Order as Model
    else:
        from apps.formulieren.models import Submission as Model
    obj = Model.objects.filter(pk=entry.object_id).first()
    if obj is None:
        messages.error(request, "De bestelling of het antwoord bestaat niet meer.")
    elif spec.resend_function()(obj):
        messages.success(request, f"'{entry.subject}' is opnieuw verstuurd.")
    else:
        messages.error(request, "Opnieuw versturen is niet gelukt. Kijk in het logboek.")
    return redirect("mails_log")

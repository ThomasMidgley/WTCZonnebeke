import logging
from io import BytesIO

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.timezone import localtime
from openpyxl import Workbook
from openpyxl.styles import Font

from .models import Submission

logger = logging.getLogger(__name__)


def save_submission(form, answers, email="", order_number="", send_confirmation=True):
    """Bewaart een antwoord en verstuurt de mails: bevestiging aan de invuller, melding aan de beheerders."""
    submission = Submission.objects.create(form=form, answers=answers, email=email, order_number=order_number)
    context = {"form": form, "submission": submission}
    if email and send_confirmation:
        from apps.core.models import Clubgegevens

        cc = Clubgegevens.load().copy_addresses(exclude=[email])
        _send(f"Bevestiging: {form.title}", "formulieren/email/confirmation.txt", context, [email], cc=cc)
    notify = form.notify_addresses()
    if notify:
        _send(f"Nieuw antwoord: {form.title}", "formulieren/email/notify.txt", context, notify,
              reply_to=[email] if email else None)
    return submission


def _send(subject, template, context, to, reply_to=None, cc=None):
    try:
        EmailMessage(subject, render_to_string(template, context), to=to, cc=cc, reply_to=reply_to).send()
    except Exception:
        logger.exception("Mail '%s' mislukt", subject)


def xlsx_response_bytes(title, header, rows):
    """Maakt een Excel-bestand: één rij per antwoord."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or "Antwoorden"
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)
    sheet.freeze_panes = "A2"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def submissions_table(form):
    """Kolommen: datum, e-mail, bestelling, elke vraag (ook vragen die intussen gewijzigd zijn) en de afvinkvakjes."""
    submissions = list(form.submissions.all().order_by("created_at"))
    labels = [q.label for q in form.questions.all()]
    for submission in submissions:
        for label, _ in submission.answers:
            if label not in labels:
                labels.append(label)
    checks = form.check_labels()
    header = ["Ingediend op", "E-mailadres", "Bestelling"] + labels + checks
    rows = []
    for submission in submissions:
        answers = dict((label, value) for label, value in submission.answers)
        rows.append(
            [localtime(submission.created_at).strftime("%d/%m/%Y %H:%M"), submission.email, submission.order_number]
            + [answers.get(label, "") for label in labels]
            + ["ja" if submission.checks.get(label) else "nee" for label in checks]
        )
    return header, rows


def save_checks(form, post):
    """Bewaart de afvinkvakjes uit de lijst met antwoorden. Enkel wijzigingen worden weggeschreven."""
    labels = form.check_labels()
    changed = 0
    for submission in form.submissions.all():
        new = {label: f"check-{submission.pk}-{index}" in post for index, label in enumerate(labels)}
        old = {label: bool(submission.checks.get(label)) for label in labels}
        if new != old:
            submission.checks = {**submission.checks, **new}
            submission.save(update_fields=["checks"])
            changed += 1
    return changed

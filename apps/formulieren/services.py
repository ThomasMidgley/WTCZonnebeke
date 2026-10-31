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
        _send(f"Bevestiging: {form.title}", "formulieren/email/confirmation.txt", context, [email])
    notify = form.notify_addresses()
    if notify:
        _send(f"Nieuw antwoord: {form.title}", "formulieren/email/notify.txt", context, notify,
              reply_to=[email] if email else None)
    return submission


def _send(subject, template, context, to, reply_to=None):
    try:
        EmailMessage(subject, render_to_string(template, context), to=to, reply_to=reply_to).send()
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
    """Kolommen: datum, e-mail, bestelling en elke vraag (ook vragen die intussen gewijzigd zijn)."""
    submissions = list(form.submissions.all().order_by("created_at"))
    labels = [q.label for q in form.questions.all()]
    for submission in submissions:
        for label, _ in submission.answers:
            if label not in labels:
                labels.append(label)
    header = ["Ingediend op", "E-mailadres", "Bestelling"] + labels
    rows = []
    for submission in submissions:
        answers = dict((label, value) for label, value in submission.answers)
        rows.append(
            [localtime(submission.created_at).strftime("%d/%m/%Y %H:%M"), submission.email, submission.order_number]
            + [answers.get(label, "") for label in labels]
        )
    return header, rows

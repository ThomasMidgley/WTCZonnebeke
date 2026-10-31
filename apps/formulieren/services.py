import logging
from io import BytesIO

from django.utils.timezone import localtime
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.mails import services as mails

from .models import Submission

logger = logging.getLogger(__name__)


def save_submission(form, answers, email="", order_number="", send_confirmation=True):
    """Bewaart een antwoord en verstuurt de mails: bevestiging aan de invuller, melding aan de beheerders.

    Bij een inschrijving via de webshop (order_number) kreeg de invuller al de bevestiging van de bestelling.
    """
    submission = Submission.objects.create(form=form, answers=answers, email=email, order_number=order_number)
    if send_confirmation:
        send_confirmation_mail(submission)
    send_notify_mail(submission)
    return submission


def _context(submission):
    from django.conf import settings

    from apps.core.models import Clubgegevens

    return {"form": submission.form, "submission": submission, "club": Clubgegevens.load(),
            "base_url": settings.WAGTAILADMIN_BASE_URL}


def send_confirmation_mail(submission):
    if not (submission.email and submission.form.send_confirmation):
        return False
    return mails.send("form_confirmation", [submission.email], _context(submission), object_id=submission.pk)


def send_notify_mail(submission):
    # Kreeg het kopie-adres van de club al een kopie (van de bevestiging), dan niet nog eens een melding.
    copied = mails.club_copy("order_confirmation" if submission.order_number else "form_confirmation")
    if not submission.order_number and not (submission.email and submission.form.send_confirmation):
        copied = None
    to = [a for a in submission.form.notify_addresses() if not copied or a.lower() != copied.lower()]
    return mails.send("form_notify", to, _context(submission), object_id=submission.pk,
                      reply_to=[submission.email] if submission.email else None)


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

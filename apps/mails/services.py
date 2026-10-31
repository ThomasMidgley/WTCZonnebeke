"""Versturen van de automatische mails: tekst van de beheerder + vast middenstuk, kopie naar de club, logboek."""

import logging
import re

from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from .models import MailLog, MailTemplate
from .registry import MAILS, values

logger = logging.getLogger(__name__)
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def fill(text, data):
    """Vult {naam}, {bestelnummer} ... in. Onbekende woorden tussen accolades blijven staan."""
    return PLACEHOLDER.sub(lambda m: str(data[m.group(1)]) if m.group(1) in data else m.group(0), text or "")


def render(key, context, template=None):
    """Geeft (onderwerp, tekst). `template` mag een niet-opgeslagen MailTemplate zijn (voorbeeld en testmail)."""
    spec = MAILS[key]
    template = template or MailTemplate.get(key)
    data = values(spec, context)
    middle = render_to_string(spec.body_template, context).strip()
    parts = [fill(template.intro, data).strip(), middle, fill(template.outro, data).strip()]
    if spec.for_customer:
        club = context["club"]
        parts.append("--\n" + "\n".join(p for p in [club.vzw_name, club.address, context.get("base_url", "")] if p))
    body = "\n\n".join(p for p in parts if p) + "\n"
    subject = " ".join(fill(template.subject, data).split())
    return subject, body


def club_copy(key):
    """Het kopie-adres van de club als deze mail in kopie gaat, anders None."""
    from apps.core.models import Clubgegevens

    template = MailTemplate.get(key)
    if not (template.enabled and template.copy_to_club and MAILS[key].can_copy):
        return None
    addresses = Clubgegevens.load().copy_addresses()
    return addresses[0] if addresses else None


def send(key, to, context, reply_to=None, object_id=None, exclude_copy=()):
    """Verstuurt één automatische mail en schrijft ze in het logboek. Geeft True als ze vertrokken is."""
    template = MailTemplate.get(key)
    to = [address for address in to if address]
    if not template.enabled or not to:
        return False
    copy = club_copy(key)
    skip = {a.lower() for a in [*to, *exclude_copy] if a}
    cc = [copy] if copy and copy.lower() not in skip else []
    subject, body = render(key, context, template)
    log = MailLog(key=key, recipients=", ".join(to + [f"kopie: {a}" for a in cc]), subject=subject[:255],
                  object_id=object_id)
    try:
        EmailMessage(subject, body, to=to, cc=cc, reply_to=reply_to).send()
    except Exception as exc:
        logger.exception("Mail '%s' naar %s mislukt", subject, to)
        log.ok = False
        log.error = str(exc)[:1000]
    log.save()
    MailLog.clean_up()
    return log.ok

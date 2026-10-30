"""E-mail versturen via Microsoft Graph (sendMail) met de app-registratie van de tenant."""

import base64
import logging

import msal
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)
GRAPH = "https://graph.microsoft.com/v1.0"


def _settings():
    from .models import Integraties

    return Integraties.load()


def graph_token():
    integraties = _settings()
    app = msal.ConfidentialClientApplication(
        integraties.client_id,
        authority=f"https://login.microsoftonline.com/{integraties.tenant_id}",
        client_credential=settings.AZURE_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Geen Graph-token: {result.get('error_description', result.get('error'))}")
    return result["access_token"]


def _recipients(addresses):
    return [{"emailAddress": {"address": address}} for address in addresses]


def _to_graph(message):
    body_type, body = "Text", message.body
    for alternative, mimetype in getattr(message, "alternatives", []):
        if mimetype == "text/html":
            body_type, body = "HTML", alternative
    payload = {
        "subject": message.subject,
        "body": {"contentType": body_type, "content": body},
        "toRecipients": _recipients(message.to),
        "ccRecipients": _recipients(message.cc),
        "bccRecipients": _recipients(message.bcc),
        "replyTo": _recipients(message.reply_to),
    }
    attachments = []
    for attachment in message.attachments:
        name, content, mimetype = attachment
        if isinstance(content, str):
            content = content.encode()
        attachments.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": mimetype or "application/octet-stream",
                "contentBytes": base64.b64encode(content).decode(),
            }
        )
    if attachments:
        payload["attachments"] = attachments
    return payload


class GraphEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sender = _settings().mail_sender
        try:
            token = graph_token()
        except Exception:
            logger.exception("Kon geen token ophalen voor e-mail")
            if not self.fail_silently:
                raise
            return 0
        sent = 0
        for message in email_messages:
            response = requests.post(
                f"{GRAPH}/users/{sender}/sendMail",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": _to_graph(message), "saveToSentItems": True},
                timeout=20,
            )
            if response.status_code == 202:
                sent += 1
            else:
                logger.error("E-mail niet verstuurd (%s): %s", response.status_code, response.text[:500])
                if not self.fail_silently:
                    response.raise_for_status()
        return sent

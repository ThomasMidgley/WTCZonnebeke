"""Nieuwe nieuwsberichten uit Cyql mailen naar de ledengroep.

Cyql geeft enkel actieve berichten terug. Een bericht wordt één keer gemaild:
wat al in NewsItem staat, slaan we over. De eerste keer (nog niets gekend)
onthouden we de bestaande berichten zonder te mailen, en een bericht ouder dan
MAX_AGE wordt ook enkel onthouden, zodat het aanzetten van het vinkje geen
reeks oude mails verstuurt.
"""

import html
import re
from datetime import timedelta

from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags

from apps.core.models import CyqlApp

from .models import NewsItem

NEWS_QUERY = """query($page: Int) { news(page: $page, pageSize: 10) {
  items { id title description publicationDate } totalCount hasNextPage } }"""
MAX_AGE = timedelta(days=7)
HTML_TAG = re.compile(r"<(p|br|div|ul|ol|li|strong|b|em|i|a|h[1-6]|span)\b", re.IGNORECASE)


def mail_parts(description):
    """(tekst, html) voor de mail. Cyql kan de beschrijving als HTML of als gewone tekst geven."""
    description = (description or "").strip()
    if HTML_TAG.search(description):
        text = html.unescape(strip_tags(re.sub(r"<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", description, flags=re.I)))
        return re.sub(r"\n{3,}", "\n\n", text).strip(), description
    paragraphs = [html.escape(part).replace("\n", "<br>") for part in re.split(r"\n\s*\n", description) if part.strip()]
    return description, "".join(f"<p>{part}</p>" for part in paragraphs)


def send_news_mail(item, to):
    text, body = mail_parts(item.get("description"))
    message = EmailMultiAlternatives(subject=(item.get("title") or "Nieuws").strip(), body=text, to=[to])
    message.attach_alternative(body, "text/html")
    message.send()


def latest_news(client):
    """De nieuwste berichten, nieuwste eerst.

    Cyql kan niet sorteren en geeft de oudste eerst. Daarom lezen we pagina 1 (voor het totaal)
    en de laatste twee pagina's, en sorteren we zelf. Zo blijven het maximaal drie kleine vragen.
    """
    first = client.query(NEWS_QUERY, {"page": 1}).get("news") or {}
    items = list(first.get("items") or [])
    if first.get("hasNextPage"):
        last = max(1, -(-(first.get("totalCount") or 0) // 10))
        for page in sorted({max(2, last - 1), last}):
            items += (client.query(NEWS_QUERY, {"page": page}).get("news") or {}).get("items") or []
    unique = {item["id"]: item for item in items if item.get("id")}
    return sorted(unique.values(), key=lambda item: item.get("publicationDate") or "", reverse=True)


def sync_news(client, now=None):
    """Geeft (samenvatting, gelukt) terug."""
    settings = CyqlApp.load()
    if not (settings.sync_news and settings.member_group):
        return "niet ingesteld", True
    now = now or timezone.now()
    items = latest_news(client)
    first_run = not NewsItem.objects.exists()
    known = {str(pk) for pk in NewsItem.objects.values_list("cyql_id", flat=True)}
    mailed, remembered, failed = [], 0, []
    for item in items:
        if not item.get("id") or str(item["id"]) in known:
            continue
        published = parse_datetime(item["publicationDate"]) if item.get("publicationDate") else None
        if published and published > now:
            continue  # nog niet gepubliceerd: komt bij een volgende sync
        record = NewsItem(cyql_id=item["id"], title=(item.get("title") or "Nieuws")[:255], published_at=published)
        if first_run or (published and now - published > MAX_AGE):
            record.save()
            remembered += 1
            continue
        try:
            send_news_mail(item, settings.member_group)
        except Exception as exc:  # opnieuw proberen bij de volgende sync
            failed.append(f"{record.title} ({exc})")
            continue
        record.mailed_at = timezone.now()
        record.save()
        mailed.append(record.title)

    parts = [f"{len(items)} actieve berichten"]
    if mailed:
        parts.append(f"gemaild naar {settings.member_group}: {', '.join(mailed)}")
    if remembered:
        parts.append(f"{remembered} bestaande berichten onthouden zonder mail" + (" (eerste keer)" if first_run else ""))
    if failed:
        parts.append(f"mail mislukt: {'; '.join(failed)}")
    if not (mailed or remembered or failed):
        parts.append("geen nieuwe berichten")
    return ", ".join(parts), not failed

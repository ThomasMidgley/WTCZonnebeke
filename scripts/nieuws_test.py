#!/usr/bin/env python3
"""Los testscript: een nieuwsbericht uit Cyql mailen naar de ledengroep, zonder de website.

Werkt met gewone Python 3.8 of nieuwer, zonder extra pakketten, op Windows, Mac of Linux.
Het doet hetzelfde als de website met het vinkje "synchroniseer nieuws", maar voor één bericht.

Wat het doet:
  1. leest de laatste actieve nieuwsberichten uit Cyql (één kleine vraag, enkele punten van het weekbudget);
  2. toont ze genummerd, met hoe de mail van bericht 1 (of --bericht N) eruit zou zien;
  3. enkel met --verstuur: mailt dat bericht via Microsoft 365 naar de groep
     (onderwerp = titel, tekst = beschrijving), vanuit het adres van --afzender.

Gebruik:
  python nieuws_test.py leden@wtczonnebeke.be
  python nieuws_test.py leden@wtczonnebeke.be --bericht 2
  python nieuws_test.py leden@wtczonnebeke.be --bericht 1 --verstuur

De sleutels komen uit de omgevingsvariabelen CYQL_API_KEY, AZURE_TENANT_ID, AZURE_CLIENT_ID en
AZURE_CLIENT_SECRET. Ontbreekt er een, dan vraagt het script erom (geheimen worden niet getoond
terwijl je typt). Er wordt niets bewaard. De app-registratie heeft het recht Mail.Send nodig
(Application), net zoals de website voor het contactformulier.
"""

import argparse
import getpass
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

CYQL = "https://api.cyql.app/api/graphql"
GRAPH = "https://graph.microsoft.com/v1.0"
NEWS_QUERY = """query($page: Int) { news(page: $page, pageSize: 5) {
  items { id title description publicationDate } totalCount hasNextPage } }"""
HTML_TAG = re.compile(r"<(p|br|div|ul|ol|li|strong|b|em|i|a|h[1-6]|span)\b", re.IGNORECASE)


def http(method, url, headers=None, data=None, form=None):
    headers = {"Accept": "application/json", **(headers or {})}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return (json.loads(raw) if raw else {}), response.headers
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")
        try:
            error = json.loads(text).get("error", {})
            if isinstance(error, dict):
                text = f"{error.get('code')}: {error.get('message')}"
        except ValueError:
            text = text[:300]
        raise RuntimeError(f"({exc.code}) {text}") from None


def ask(name, label, secret=False):
    value = os.environ.get(name, "").strip()
    if not value:
        value = (getpass.getpass if secret else input)(f"{label}: ").strip()
    if not value:
        sys.exit(f"{label} is nodig.")
    return value


def mail_parts(description):
    """(tekst, html), net zoals de website: Cyql kan HTML of gewone tekst geven."""
    description = (description or "").strip()
    if HTML_TAG.search(description):
        text = re.sub(r"<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", description, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
        return re.sub(r"\n{3,}", "\n\n", text).strip(), description
    paragraphs = [html.escape(part).replace("\n", "<br>") for part in re.split(r"\n\s*\n", description) if part.strip()]
    return description, "".join(f"<p>{part}</p>" for part in paragraphs)


def main():
    parser = argparse.ArgumentParser(description="Mail één Cyql-nieuwsbericht naar de ledengroep.")
    parser.add_argument("groep", help="e-mailadres van de groep, bv. leden@wtczonnebeke.be")
    parser.add_argument("--bericht", type=int, default=1, help="nummer van het bericht in de lijst (standaard 1)")
    parser.add_argument("--afzender", default=os.environ.get("DEFAULT_FROM_EMAIL", ""), help="mailbox waaruit de mail vertrekt")
    parser.add_argument("--verstuur", action="store_true", help="de mail echt versturen (anders enkel tonen)")
    args = parser.parse_args()

    print("== 1. Nieuws lezen uit Cyql")
    key = ask("CYQL_API_KEY", "Cyql API-sleutel", secret=True)
    # Cyql kan niet sorteren en geeft de oudste eerst: lees pagina 1 en de laatste pagina's, sorteer zelf.
    def page(number):
        try:
            body, headers = http("POST", CYQL, {"X-Api-Key": key}, data={"query": NEWS_QUERY, "variables": {"page": number}})
        except RuntimeError as exc:
            sys.exit(f"Cyql gaf een fout {exc}")
        if body.get("errors"):
            sys.exit(f"Cyql gaf een fout: {body['errors'][0].get('message')}")
        return (body.get("data") or {}).get("news") or {}, headers

    first, headers = page(1)
    items = list(first.get("items") or [])
    if first.get("hasNextPage"):
        last = max(1, -(-(first.get("totalCount") or 0) // 5))
        for number in sorted({max(2, last - 1), last}):
            result, headers = page(number)
            items += result.get("items") or []
    items = sorted({i["id"]: i for i in items if i.get("id")}.values(), key=lambda i: i.get("publicationDate") or "", reverse=True)[:5]
    remaining = headers.get("X-RateLimit-Remaining-Club")
    if remaining not in (None, "-1"):
        print(f"Resterend weekbudget Cyql: {remaining}")
    if not items:
        sys.exit("Cyql geeft geen actieve nieuwsberichten terug.")
    print("Nieuwste eerst:")
    for number, item in enumerate(items, start=1):
        print(f"  {number}. {(item.get('publicationDate') or '')[:16].replace('T', ' ')}  {item.get('title')}")
    if not 1 <= args.bericht <= len(items):
        sys.exit(f"--bericht moet tussen 1 en {len(items)} liggen.")
    item = items[args.bericht - 1]
    subject = (item.get("title") or "Nieuws").strip()
    text, body_html = mail_parts(item.get("description"))

    print(f"\n== 2. De mail (bericht {args.bericht})")
    print(f"Aan: {args.groep}\nOnderwerp: {subject}\n\n{text}\n")
    if not args.verstuur:
        print("Niets verstuurd. Voeg --verstuur toe om deze mail echt naar de groep te sturen.")
        return

    print("== 3. Versturen via Microsoft 365")
    sender = args.afzender or ask("DEFAULT_FROM_EMAIL", "Afzender (mailbox, bv. info@...)")
    tenant = ask("AZURE_TENANT_ID", "Tenant-ID")
    client = ask("AZURE_CLIENT_ID", "Client-ID (application ID)")
    secret = ask("AZURE_CLIENT_SECRET", "Client secret (waarde, niet het secret-ID)", secret=True)
    try:
        token, _ = http(
            "POST",
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            form={
                "client_id": client,
                "client_secret": secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        http(
            "POST",
            f"{GRAPH}/users/{sender}/sendMail",
            {"Authorization": f"Bearer {token['access_token']}"},
            data={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": body_html},
                    "toRecipients": [{"emailAddress": {"address": args.groep}}],
                },
                "saveToSentItems": True,
            },
        )
    except RuntimeError as exc:
        sys.exit(f"Versturen mislukt {exc}\n(403: heeft de app het recht Mail.Send als Application, met admin consent?)")
    print(f"Verstuurd van {sender} naar {args.groep}. Kijk ook in de spammap.")


if __name__ == "__main__":
    main()

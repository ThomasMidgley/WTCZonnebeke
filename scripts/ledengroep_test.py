#!/usr/bin/env python3
"""Los testscript voor de ledengroep in Microsoft 365, zonder de website en zonder Cyql.

Werkt met gewone Python 3.8 of nieuwer, zonder extra pakketten, op Windows, Mac of Linux.

Wat het doet:
  1. vraagt een token aan met de app-registratie (zoals de website dat doet);
  2. toont welke rechten (roles) Microsoft echt in dat token zet, en welke ontbreken;
  3. zoekt de groep op via haar e-mailadres en leest de leden;
  4. enkel met --uitvoeren: zet het testadres als gast in de tenant (zonder mail) en voegt het toe aan de groep.

Gebruik:
  python ledengroep_test.py leden@wtczonnebeke.be
  python ledengroep_test.py leden@wtczonnebeke.be --test-adres iemand@gmail.com
  python ledengroep_test.py leden@wtczonnebeke.be --test-adres iemand@gmail.com --uitvoeren

Tenant-ID, client-ID en geheim komen uit de omgevingsvariabelen AZURE_TENANT_ID,
AZURE_CLIENT_ID en AZURE_CLIENT_SECRET. Ontbreekt er een, dan vraagt het script erom
(het geheim wordt niet getoond terwijl je het typt). Er wordt niets bewaard.
"""

import argparse
import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

GRAPH = "https://graph.microsoft.com/v1.0"
NEEDED = {
    "GroupMember.Read.All": "groep opzoeken en leden lezen",
    "User.Read.All": "e-mailadressen van de leden lezen",
    "User.Invite.All": "gasten aanmaken",
    "GroupMember.ReadWrite.All": "leden toevoegen en verwijderen",
}


class GraphError(Exception):
    def __init__(self, status, text):
        self.status = status
        try:
            error = json.loads(text).get("error", {})
            if isinstance(error, dict):
                text = f"{error.get('code')}: {error.get('message')}"
            else:
                text = f"{error}: {json.loads(text).get('error_description', '')}"
        except ValueError:
            text = text[:300]
        super().__init__(f"({status}) {text}")


def http(method, url, token=None, data=None, form=None):
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise GraphError(exc.code, exc.read().decode(errors="replace")) from None


def get_all(token, url):
    items = []
    while url:
        data = http("GET", url, token)
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items


def ask(name, label, secret=False):
    value = os.environ.get(name, "").strip()
    if not value:
        value = (getpass.getpass if secret else input)(f"{label}: ").strip()
    if not value:
        sys.exit(f"{label} is nodig.")
    return value


def step(title):
    print(f"\n== {title}")


def main():
    parser = argparse.ArgumentParser(description="Test de ledengroep in Microsoft 365 zonder Cyql.")
    parser.add_argument("groep", help="e-mailadres van de groep, bv. leden@wtczonnebeke.be")
    parser.add_argument("--test-adres", help="één extern adres om als gast toe te voegen")
    parser.add_argument("--uitvoeren", action="store_true", help="het testadres echt toevoegen (anders enkel lezen)")
    args = parser.parse_args()
    if args.uitvoeren and not args.test_adres:
        sys.exit("--uitvoeren heeft een --test-adres nodig.")

    tenant = ask("AZURE_TENANT_ID", "Tenant-ID")
    client = ask("AZURE_CLIENT_ID", "Client-ID (application ID)")
    secret = ask("AZURE_CLIENT_SECRET", "Client secret (waarde, niet het secret-ID)", secret=True)

    step("1. Token aanvragen")
    try:
        result = http(
            "POST",
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            form={
                "client_id": client,
                "client_secret": secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
    except GraphError as exc:
        sys.exit(f"Geen token: {exc}\nControleer tenant-ID, client-ID en of het geheim nog geldig is.")
    token = result["access_token"]
    part = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    roles = sorted(claims.get("roles", []))
    print(f"OK. App: {claims.get('app_displayname', '?')}  tenant: {claims.get('tid', '?')}")

    step("2. Rechten in het token")
    print("Aanwezig:", ", ".join(roles) or "GEEN")
    missing = [role for role in NEEDED if role not in roles]
    for role, purpose in NEEDED.items():
        print(f"  [{'x' if role in roles else ' '}] {role:28} {purpose}")
    if missing:
        print(
            "\nMicrosoft geeft deze rechten NIET aan de app: " + ", ".join(missing) + ".\n"
            "In Entra > App registrations > (de app) > API permissions:\n"
            "  - het type moet 'Application' zijn, niet 'Delegated' (Delegated telt hier niet mee);\n"
            "  - de status moet een groen vinkje 'Granted for ...' tonen (knop 'Grant admin consent');\n"
            "  - na een wijziging kan het enkele minuten duren voor een nieuw token de rechten bevat."
        )

    step("3. Groep opzoeken")
    address = args.groep.replace("'", "")
    try:
        groups = get_all(
            token,
            f"{GRAPH}/groups?" + urllib.parse.urlencode({"$filter": f"mail eq '{address}'", "$select": "id,displayName,mail,groupTypes,mailEnabled,securityEnabled"}),
        )
    except GraphError as exc:
        sys.exit(f"Groep opzoeken mislukt {exc}")
    if not groups:
        sys.exit(f"Geen groep gevonden met adres {address}. Is het de juiste tenant en het juiste adres?")
    group = groups[0]
    kind = "Microsoft 365-groep" if "Unified" in (group.get("groupTypes") or []) else "geen Microsoft 365-groep (distributielijst of beveiligingsgroep?)"
    print(f"Gevonden: {group.get('displayName')} <{group.get('mail')}>, {kind}")
    if "Unified" not in (group.get("groupTypes") or []):
        print("Let op: leden van een distributielijst of mail-enabled beveiligingsgroep kan Graph niet wijzigen.")

    step("4. Leden lezen")
    try:
        members = get_all(
            token,
            f"{GRAPH}/groups/{group['id']}/members/microsoft.graph.user?" + urllib.parse.urlencode({"$select": "id,displayName,mail,otherMails,userType", "$top": "999"}),
        )
    except GraphError as exc:
        sys.exit(f"Leden lezen mislukt {exc}")
    guests = [m for m in members if m.get("userType") == "Guest"]
    print(f"{len(members)} leden, waarvan {len(guests)} gasten:")
    present = set()
    for member in members:
        addresses = {a.lower() for a in [member.get("mail"), *(member.get("otherMails") or [])] if a}
        present |= addresses
        print(f"  - {member.get('displayName') or '?':30} {', '.join(sorted(addresses)) or '(adres niet leesbaar)'}  {member.get('userType') or ''}")

    if not args.test_adres:
        print("\nKlaar. Geef --test-adres mee om ook het toevoegen te testen.")
        return
    email = args.test_adres.strip().lower()
    step(f"5. Testadres {email}")
    if email in present:
        print("Staat al in de groep, er hoeft niets te gebeuren.")
        return
    if not args.uitvoeren:
        print("Zou als gast aangemaakt en aan de groep toegevoegd worden. Voeg --uitvoeren toe om het echt te doen.")
        return
    try:
        invited = http(
            "POST",
            f"{GRAPH}/invitations",
            token,
            data={
                "invitedUserEmailAddress": email,
                "invitedUserDisplayName": email,
                "inviteRedirectUrl": "https://myapps.microsoft.com",
                "sendInvitationMessage": False,
            },
        )
    except GraphError as exc:
        sys.exit(f"Gast aanmaken mislukt {exc}")
    user_id = invited["invitedUser"]["id"]
    print(f"Gast bestaat in de tenant (id {user_id}).")
    try:
        http("POST", f"{GRAPH}/groups/{group['id']}/members/$ref", token, data={"@odata.id": f"{GRAPH}/directoryObjects/{user_id}"})
    except GraphError as exc:
        if exc.status == 400 and "already exist" in str(exc):
            print("Was al lid van de groep.")
            return
        sys.exit(f"Toevoegen aan de groep mislukt {exc}")
    print("Toegevoegd aan de groep. Stuur een testmail naar de groep om te zien of het adres hem ontvangt.")


if __name__ == "__main__":
    main()

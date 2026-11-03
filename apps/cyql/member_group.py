"""Houdt de Microsoft 365-groep met de leden (bv. leden@...) gelijk met de goedgekeurde Cyql-leden.

Leden komen als gast in de tenant, zonder uitnodigingsmail. Enkel gasten worden
toegevoegd of verwijderd: gebruikers van de tenant zelf (het bestuur) blijven
altijd in de groep. Een verwijderd lid blijft gast in de tenant, maar krijgt de
groepsmails niet meer.

Nodige rechten van de app-registratie (toepassing, met beheerderstoestemming):
GroupMember.Read.All (groep opzoeken), User.Read.All (adressen van de leden lezen),
User.Invite.All (gasten aanmaken) en GroupMember.ReadWrite.All (leden toevoegen en verwijderen).
"""

import logging
import time

import requests

from apps.core.mail import GRAPH, graph_token
from apps.core.models import CyqlApp

from .models import Member

logger = logging.getLogger(__name__)
TIMEOUT = 20


class MemberGroupError(Exception):
    pass


class Graph:
    def __init__(self, token=None):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token or graph_token()}"

    def request(self, method, url, **kwargs):
        url = url if url.startswith("https://") else f"{GRAPH}{url}"
        for attempt in range(3):
            response = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
            if response.status_code != 429:
                return response
            # Te veel vragen na elkaar: Microsoft zegt hoe lang we moeten wachten.
            time.sleep(min(int(response.headers.get("Retry-After", 5)), 30))
        return response

    def get_all(self, url, params=None, action="lezen uit Microsoft 365"):
        items = []
        while url:
            response = self.request("GET", url, params=params)
            check(response, action)
            data = response.json()
            items.extend(data.get("value", []))
            url, params = data.get("@odata.nextLink"), None
        return items


def check(response, action):
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
            detail = f"{error.get('code')}: {error.get('message')}"
        except ValueError:
            detail = response.text[:200]
        if response.status_code == 403:
            detail += (
                " (ontbreekt een recht of de admin consent? Nodig: GroupMember.Read.All, User.Read.All, "
                "User.Invite.All en GroupMember.ReadWrite.All)"
            )
        raise MemberGroupError(f"{action} mislukt ({response.status_code}) {detail}")


def wanted_members(settings):
    """E-mailadres -> naam van wie in de groep hoort."""
    if settings.member_group_test_emails:
        return {email: email for email in settings.member_group_test_emails}
    return {member.email.lower(): str(member) for member in Member.objects.exclude(email="")}


def find_group(graph, address):
    groups = graph.get_all("/groups", {"$filter": f"mail eq '{address.replace(chr(39), '')}'", "$select": "id"}, "groep opzoeken")
    if not groups:
        raise MemberGroupError(f"geen groep gevonden met adres {address}")
    return groups[0]["id"]


def user_addresses(user):
    return {address.lower() for address in [user.get("mail"), *(user.get("otherMails") or [])] if address}


def sync_member_group(graph=None, deadline=None):
    """Werkt de groep bij en geeft een korte samenvatting voor het verslag.

    `deadline` (time.monotonic) beperkt hoe lang we toevoegen; wat niet lukt, volgt bij de volgende sync.
    """
    settings = CyqlApp.load()
    if not settings.member_group:
        return "niet ingesteld"
    wanted = wanted_members(settings)
    graph = graph or Graph()
    group_id = find_group(graph, settings.member_group)
    unreadable = 0
    users = graph.get_all(
        f"/groups/{group_id}/members/microsoft.graph.user",
        {"$select": "id,mail,otherMails,userType", "$top": "999"},
        "groepsleden lezen",
    )
    present = set()
    guests = []
    for user in users:
        present |= user_addresses(user)
        if not user_addresses(user):
            # Zonder User.Read.All geeft Microsoft enkel het ID: wie we niet kunnen lezen, halen we nooit weg.
            unreadable += 1
        elif user.get("userType") == "Guest":
            guests.append(user)

    to_add = sorted(set(wanted) - present)
    to_remove = [guest for guest in guests if not user_addresses(guest) & set(wanted)]

    added, failed, postponed = 0, [], 0
    for index, email in enumerate(to_add):
        if deadline and time.monotonic() > deadline:
            postponed = len(to_add) - index
            break
        try:
            add_guest(graph, group_id, email, wanted[email])
            added += 1
        except MemberGroupError as exc:
            failed.append(email)
            logger.warning("Ledengroep: %s niet toegevoegd: %s", email, exc)

    removed = 0
    skipped_removal = ""
    if not wanted:
        skipped_removal = "niemand verwijderd omdat de ledenlijst leeg is"
    elif len(to_remove) > max(5, len(guests) // 2):
        # Meer dan de helft in één keer weg wijst eerder op een fout dan op een echte wijziging.
        skipped_removal = f"{len(to_remove)} te verwijderen gasten niet verwijderd (meer dan de helft, controleer)"
    else:
        for guest in to_remove:
            response = graph.request("DELETE", f"/groups/{group_id}/members/{guest['id']}/$ref")
            if response.status_code != 404:
                check(response, "verwijderen uit de groep")
            removed += 1

    parts = [f"{len(wanted)} adressen gewenst", f"{added} toegevoegd", f"{removed} verwijderd"]
    if postponed:
        parts.append(f"{postponed} volgen bij de volgende sync")
    if failed:
        parts.append(f"niet gelukt voor {', '.join(failed[:5])}{' ...' if len(failed) > 5 else ''}")
    if skipped_removal:
        parts.append(skipped_removal)
    if unreadable:
        parts.append(f"van {unreadable} groepsleden is het adres niet leesbaar (recht User.Read.All?), zij blijven staan")
    return ", ".join(parts)


def add_guest(graph, group_id, email, name):
    # Bestaat de gast al, dan geeft Microsoft dezelfde gebruiker terug.
    response = graph.request(
        "POST",
        "/invitations",
        json={
            "invitedUserEmailAddress": email,
            "invitedUserDisplayName": name,
            "inviteRedirectUrl": "https://myapps.microsoft.com",
            "sendInvitationMessage": False,
        },
    )
    check(response, "gast aanmaken")
    user_id = response.json()["invitedUser"]["id"]
    response = graph.request(
        "POST",
        f"/groups/{group_id}/members/$ref",
        json={"@odata.id": f"{GRAPH}/directoryObjects/{user_id}"},
    )
    if response.status_code == 400 and "already exist" in response.text:
        return
    check(response, "toevoegen aan de groep")

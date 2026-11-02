"""Herinschrijving: de leden uit het lidgeldformulier vergelijken met de leden in Cyql.

Drie gevallen:
- in de lijst én in Cyql: niets te doen;
- in de lijst, nog niet in Cyql: het lid meldt zich zelf aan, of de club importeert het (csv "Import Cyql");
- in Cyql, niet in de lijst: niet heringeschreven, de club zet het manueel inactief in Cyql (export "Inactieve leden").

De Cyql-API kan enkel lezen; leden toevoegen, uitschakelen of verwijderen gaat alleen in Cyql zelf.
Een lid telt als gevonden bij dezelfde voor- en familienaam, of anders bij hetzelfde e-mailadres.
"""

import unicodedata
from dataclasses import dataclass

FIRST_NAME_LABELS = ("Voornaam",)
LAST_NAME_LABELS = ("Naam", "Familienaam", "Achternaam")
EMAIL_LABELS = ("E-mailadres", "E-mail", "Email")


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().replace("-", " ").split())


def first_answer(answers, labels):
    for label in labels:
        value = (answers.get(label) or "").strip()
        if value:
            return value
    return ""


@dataclass
class Person:
    first_name: str
    last_name: str
    email: str

    @property
    def name_key(self):
        return (normalize(self.first_name), normalize(self.last_name))

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


def people_from_form(form):
    """Elke persoon uit de antwoorden, één keer (ook als iemand twee keer ingeschreven werd)."""
    people, seen = [], set()
    for submission in form.submissions.all().order_by("created_at"):
        answers = dict((label, str(value)) for label, value in submission.answers)
        person = Person(
            first_name=first_answer(answers, FIRST_NAME_LABELS),
            last_name=first_answer(answers, LAST_NAME_LABELS),
            email=(first_answer(answers, EMAIL_LABELS) or submission.email or "").lower(),
        )
        key = person.name_key if any(person.name_key) else ("", person.email)
        if key in seen:
            continue
        seen.add(key)
        people.append(person)
    return people


def compare(form):
    """Geeft (in beide, enkel in de lijst, enkel in Cyql)."""
    from apps.cyql.models import Member

    members = [Person(m.first_name, m.last_name, (m.email or "").lower()) for m in Member.objects.all()]
    by_name = {m.name_key: m for m in members}
    by_email = {}
    for member in members:
        if member.email:
            by_email.setdefault(member.email, member)

    both, only_list, matched = [], [], set()
    for person in people_from_form(form):
        member = by_name.get(person.name_key)
        if member is None and person.email:
            candidate = by_email.get(person.email)
            # Gezinsleden delen soms één e-mailadres: enkel koppelen als die naam nog niet gekoppeld is.
            if candidate is not None and id(candidate) not in matched:
                member = candidate
        if member is None:
            only_list.append(person)
        else:
            matched.add(id(member))
            both.append((person, member))
    only_cyql = [member for member in members if id(member) not in matched]
    return both, only_list, only_cyql

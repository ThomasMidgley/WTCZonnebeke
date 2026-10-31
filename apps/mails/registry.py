"""Alle automatische mails van de website: wanneer ze vertrekken, naar wie, en de standaardtekst.

Het middenstuk van elke mail (de bestelling, de antwoorden, de links) komt uit een vaste template
en is niet aan te passen; onderwerp, tekst boven en tekst onder past een beheerder aan in het menu E-mails.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace

from django.utils.module_loading import import_string

from apps.core.templatetags.wtc import euro

SIGNATURE = "Sportieve groeten,\n{club}"


@dataclass
class MailSpec:
    key: str
    label: str
    when: str
    to: str
    body_template: str
    kind: str  # "order" of "submission": waarmee je de mail opnieuw verstuurt
    subject: str
    intro: str = ""
    outro: str = ""
    copy_to_club: bool = False
    can_copy: bool = True
    for_customer: bool = True  # klantmails krijgen onderaan de gegevens van de club
    placeholders: list = field(default_factory=list)
    resend: str = ""  # functie die de mail opnieuw verstuurt voor een bestelling of antwoord

    def defaults(self):
        return {
            "subject": self.subject, "intro": self.intro, "outro": self.outro,
            "enabled": True, "copy_to_club": self.copy_to_club and self.can_copy,
        }

    def resend_function(self):
        return import_string(self.resend)


ORDER_FIELDS = [
    ("naam", "naam van de besteller"),
    ("bestelnummer", "bv. 2026-0042"),
    ("totaal", "bv. € 130"),
    ("club", "naam van de vzw"),
]
FORM_FIELDS = [("formulier", "titel van het formulier"), ("club", "naam van de vzw")]

MAILS = {
    spec.key: spec
    for spec in [
        MailSpec(
            key="order_confirmation", label="Bevestiging bestelling",
            when="Zodra Stripe de betaling bevestigt (ook voor inschrijvingen en lidgeld)", to="Besteller",
            body_template="mails/body/order_confirmation.txt", kind="order",
            subject="Bevestiging bestelling {bestelnummer}",
            intro="Beste {naam},\n\nBedankt voor je bestelling bij {club}. Je betaling is goed ontvangen.",
            outro=SIGNATURE, copy_to_club=True, placeholders=ORDER_FIELDS,
            resend="apps.shop.services.send_confirmation_mail",
        ),
        MailSpec(
            key="order_new", label="Nieuwe bestelling (stockbeheer)",
            when="Na betaling, enkel als er kledij in de bestelling zit", to="Stockbeheerders (Instellingen > Toegang)",
            body_template="mails/body/order_new.txt", kind="order",
            subject="Nieuwe bestelling {bestelnummer}",
            intro="Nieuwe betaalde bestelling {bestelnummer}.", for_customer=False, placeholders=ORDER_FIELDS,
            resend="apps.shop.services.send_stock_mail",
        ),
        MailSpec(
            key="order_ready", label="Bestelling ligt klaar",
            when="De stockbeheerder tikt op 'Ligt klaar' in de stock-app", to="Besteller",
            body_template="mails/body/order_ready.txt", kind="order",
            subject="Je bestelling {bestelnummer} ligt klaar",
            intro="Beste {naam},\n\nJe bestelling {bestelnummer} ligt klaar.",
            outro="Haal ze af bij de kledijverantwoordelijke na een clubrit of na afspraak.\n"
            "Volgens het clubreglement mag het bestuur niet afgehaalde kledij na 4 weken terug in voorraad plaatsen.\n\n"
            + SIGNATURE,
            placeholders=ORDER_FIELDS, resend="apps.shop.services.send_ready_mail",
        ),
        MailSpec(
            key="membership_welcome", label="Welkom: meld je aan in Cyql",
            when="Na betaling, als er lidgeld in de bestelling zit", to="Besteller",
            body_template="mails/body/membership_welcome.txt", kind="order",
            subject="Welkom bij WTC Zonnebeke: meld je aan in Cyql",
            intro="Beste {naam},\n\nWelkom bij {club}! Je lidgeld is betaald.\n\n"
            "Nog één stap: meld je aan in de Cyql-app. Daar vind je de clubkalender en het klassement, "
            "en zo weet het bestuur dat je lid bent.",
            outro="Tot op de fiets!\n\n" + SIGNATURE,
            placeholders=ORDER_FIELDS + [("cyql_link", "uitnodigingslink uit Cyql > Instellingen")],
            resend="apps.shop.services.send_membership_mail",
        ),
        MailSpec(
            key="form_confirmation", label="Bevestiging formulier",
            when="Iemand vult een formulier in dat een vraag van het type e-mail heeft "
            "(niet bij inschrijvingen via de webshop: die krijgen de bevestiging van de bestelling)",
            to="Invuller", body_template="mails/body/form_confirmation.txt", kind="submission",
            subject="Bevestiging: {formulier}", intro="Hallo,", outro=SIGNATURE, copy_to_club=True,
            placeholders=FORM_FIELDS, resend="apps.formulieren.services.send_confirmation_mail",
        ),
        MailSpec(
            key="form_notify", label="Nieuw antwoord op een formulier",
            when="Elk antwoord op een formulier, ook inschrijvingen en lidgeld via de webshop",
            to="'Meldingen naar' van het formulier (het kopie-adres van de club wordt overgeslagen als het al een kopie kreeg)",
            body_template="mails/body/form_notify.txt", kind="submission",
            subject="Nieuw antwoord: {formulier}", intro='Nieuw antwoord op "{formulier}".',
            outro="Alle antwoorden bekijken en exporteren: in de beheeromgeving, menu Formulieren.",
            can_copy=False, for_customer=False, placeholders=FORM_FIELDS,
            resend="apps.formulieren.services.send_notify_mail",
        ),
    ]
}

# Wordt niet hier beheerd, maar hoort wel in het overzicht.
CONTACT_INFO = {
    "label": "Contactformulier",
    "when": "Iemand gebruikt de contactpagina",
    "to": "'Naar-adres' van de contactpagina; antwoorden gaan rechtstreeks naar de afzender",
    "where": "Onderwerp en ontvanger pas je aan op de contactpagina zelf (Pagina's > Contact > Formulier).",
}


# ---------------------------------------------------------------- invulvelden en voorbeelden


def values(spec, context):
    club = context["club"]
    result = {"club": club.vzw_name.removesuffix(" vzw") if club.vzw_name else "WTC Zonnebeke"}
    if spec.kind == "order":
        order = context["order"]
        result.update(naam=order.name, bestelnummer=order.number, totaal=f"€ {euro(order.total)}")
        result["cyql_link"] = context["cyql"].invite_link or ""
    else:
        result["formulier"] = context["form"].title
    return result


def sample_context(spec):
    """Een fictieve bestelling of een fictief antwoord, voor het voorbeeld en de testmail."""
    from django.conf import settings

    from apps.core.models import Clubgegevens, CyqlApp

    context = {"club": Clubgegevens.load(), "cyql": CyqlApp.load(), "base_url": settings.WAGTAILADMIN_BASE_URL}
    if spec.kind == "order":
        lines = [
            SimpleNamespace(quantity=1, title="Trui korte mouw", size="Heren M", is_preorder=False,
                            unit_price=Decimal("41"), line_total=Decimal("41"), answers=[]),
            SimpleNamespace(quantity=1, title="1e aansluiting", size="", is_preorder=False, unit_price=Decimal("65"),
                            line_total=Decimal("65"),
                            answers=[["Rijksregisternummer", "80.05.01-123.10"], ["Naam", "Peeters"],
                                     ["Voornaam", "Jan"]]),
        ]
        context["order"] = SimpleNamespace(
            pk=0, number="2026-0042", token="voorbeeld", name="Jan Peeters", email="jan@example.com",
            phone="+32470123456", note="", total=Decimal("106"), has_goods=True, has_preorder=False,
        )
        context["lines"] = lines
        context["extra_texts"] = ["Voorbeeld van een extra tekst bij een event, bv. het uur en de zaal."]
    else:
        context["form"] = SimpleNamespace(title="Vrijwilligers WaCaCa", thanks="Bedankt! We hebben je antwoorden goed ontvangen.")
        context["submission"] = SimpleNamespace(
            pk=0, order_number="", answers=[["Naam", "An Peeters"], ["Welke shift?", "Namiddag"]],
        )
    return context

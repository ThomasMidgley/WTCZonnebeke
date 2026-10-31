"""
Vult een lege database met de startinhoud van de website.

Veilig om opnieuw te draaien: wat al bestaat, wordt niet overschreven.
Gebruik: python manage.py seed_site
"""

import datetime
import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.contrib.forms.utils import get_field_clean_name
from wagtail.contrib.redirects.models import Redirect
from wagtail.models import Page, Site

from apps.core.models import Clubgegevens, CyqlApp, Integraties, QrInfo, Sponsor, Statuten, Toegang
from apps.pages.models import (
    BoardMember,
    BoardPage,
    CalendarPage,
    ContactFormField,
    ContactPage,
    ContentPage,
    CyqlPage,
    DownloadsPage,
    EventIndexPage,
    EventPage,
    HomePage,
    RankingPage,
    RulesPage,
)
from apps.shop.models import ShopPage
from apps.shop.seed import seed_membership, seed_shop

SEED_DIR = Path(settings.BASE_DIR) / "seed"


def stream(*blocks):
    return json.dumps([{"type": kind, "value": value} for kind, value in blocks])


BOARD = [
    ("Frankie Vandermeiren", "Voorzitter", [
        "Algemene coördinatie van de club",
        "Verantwoordelijke werkgroep MTB en VTT",
        "Vertegenwoordiging sportraad en kalendervergadering VBR",
        "Sponsoring en promotie van de club",
    ]),
    ("Evy Schotte", "Secretaris", [
        "Aansluiting nieuwe leden",
        "Ongevallenverzekering",
        "Aanvraag evenementen en reservatie van zalen en materiaal",
        "Clubkalender",
        "Verslag van de bestuursvergaderingen",
    ]),
    ("Steve Vermeulen", "Penningmeester", [
        "Financieel beheer van de vzw",
        "Beleidssubsidie",
        "Facturen sponsoring en opvolging betalingen",
    ]),
    ("Sibile Pollet", "Bestuurslid", [
        "Nieuwsbrieven, sociale media en WhatsApp",
        "Vertegenwoordiging sportraad",
    ]),
    ("Robin Depoorter", "Bestuurslid", ["Organisatie clubfeest en tussentijdse evenementen"]),
    ("Stijn Vermeulen", "Bestuurslid", [
        "Werkgroep MTB en VTT",
        "Parcours zondagritten",
        "Winteractiviteiten",
        "Sponsoring",
    ]),
    ("Kris Dewitte", "Bestuurslid", ["Werkgroep MTB en VTT", "Parcours zondagritten"]),
    ("Xavier Ceuninck", "Bestuurslid", [
        "Werkgroep MTB en VTT",
        "Beheer en stockage materiaal",
        "Clubkledij: stock en bestellingen",
    ]),
    ("Yvan Devacht", "Bestuurslid", [
        "Puntenklassement",
        "Werkgroep MTB en VTT",
        "Vertegenwoordiging kalendervergadering VBR",
    ]),
]

SPONSORS = [
    ("Fietstechniek Gheysen", "https://www.fietstechniek.be/"),
    ("De Oude Timmerie", "https://oudetimmerie.be/"),
    ("Garage Ghesquiere", "https://www.garage-ghesquiere.be/"),
    ("Deneut Sanitair", "https://deneut-technics.be/"),
]

# Oude adressen van de vorige website, zodat links in Google en oude mails blijven werken.
LEGACY_REDIRECTS = {
    "/pagina/100": "home",
    "/pagina/170": "bestuur",
    "/pagina/160": "clubreglement",
    "/inschrijving/150": "lid-worden",
    "/members/inschrijvingsform_pcn.php": "lid-worden",
    "/contact/contact-gegevens.php": "contact",
    "/contact/contact-form.php": "contact",
    "/events/clubkalender.php": "kalender",
    "/activiteiten/activiteiten.php": "kalender",
    "/data/cyclo_punten_klassement.php": "klassement",
    "/data/vbr_km_klassement.php": "klassement",
    "/data/mtb_punten_klassement.php": "klassement",
}


class Command(BaseCommand):
    help = "Maakt de startinhoud aan (pagina's, instellingen, sponsors, doorverwijzingen)."

    @transaction.atomic
    def handle(self, *args, **options):
        home = self.home()
        pages = {"home": home}
        pages["lid-worden"] = self.lid_worden(home)
        events = self.events(home)
        pages["evenementen"] = events
        pages["kalender"] = self.child(home, CalendarPage, "Clubkalender", "kalender",
                                       intro="Alle clubritten, uitstappen en activiteiten op een rij.")
        pages["klassement"] = self.child(home, RankingPage, "Klassement", "klassement",
                                         intro="Wie reed het meest mee dit seizoen? De stand van het punten- en kilometerklassement.")
        pages["bestuur"] = self.board(home)
        pages["clubreglement"] = self.rules(home)
        pages["cyql"] = self.cyql(home)
        pages["shop"] = self.child(
            home, ShopPage, "Webshop", "shop",
            intro="Bestel hier je clubkledij van Bioracer en schrijf je in voor clubevents. Betalen gaat online met "
            "Bancontact, kaart, Apple Pay of Google Pay. Kledij haal je af bij de verantwoordelijke clubkledij; "
            "je krijgt een mail zodra ze klaarligt.",
        )
        pages["downloads"] = self.downloads(home, pages["shop"])
        seed_shop()
        seed_membership()
        pages["contact"] = self.contact(home)
        self.settings()
        self.sponsors()
        self.redirects(pages)
        if home.hero_button_page_id is None:
            home.hero_button_page = pages["lid-worden"]
            home.save_revision().publish()
        self.stdout.write(self.style.SUCCESS("Startinhoud is klaar."))

    # Pagina's -----------------------------------------------------------------

    def publish(self, parent, page):
        parent.add_child(instance=page)
        page.save_revision().publish()
        return page

    def child(self, parent, model, title, slug, show_in_menus=True, **fields):
        existing = model.objects.child_of(parent).filter(slug=slug).first()
        if existing:
            return existing
        return self.publish(parent, model(title=title, slug=slug, show_in_menus=show_in_menus, **fields))

    def home(self):
        home = HomePage.objects.first()
        if home:
            return home
        root = Page.get_first_root_node()
        # Wagtail maakt standaard een "Welcome"-pagina aan; die vervangen we.
        for page in root.get_children():
            if page.specific_class is Page:
                page.delete()
        home = HomePage(
            title="Home",
            slug="home",
            hero_title="Samen uit, samen thuis",
            hero_text="Fietsclub uit Zonnebeke sinds 1988. Vier groepen, één club: "
            "of je nu sportief of rustig rijdt, je fietst altijd met mensen van jouw niveau.",
            hero_button_label="Kom eens meerijden",
            body=stream(
                ("heading", "Welkom bij WTC Zonnebeke"),
                ("paragraph",
                 "<p>WTC Zonnebeke is een gezellige fietsclub met thuisbasis in Zonnebeke. Ook wielertoeristen uit de "
                 "omliggende gemeenten zijn van harte welkom. Sinds onze oprichting in 1988 willen we een warme en "
                 "toegankelijke club zijn, waar elk lid zich thuis voelt. Jong of oud, ervaren of net begonnen: bij ons "
                 "fiets je onder het motto <b>samen uit, samen thuis</b>.</p>"),
                ("heading", "Vier groepen, elk op eigen tempo"),
                ("paragraph",
                 "<p>Het cijfer in de naam van elke groep is de gemiddelde snelheid. Zo rij je altijd met clubgenoten "
                 "van een gelijkaardig niveau, en dat maakt fietsen veiliger en leuker. Wisselen van groep kan altijd.</p>"),
                ("cards", {"cards": [
                    {"title": "A30+", "text": "Gemiddeld 30 km/u of meer\n80 tot 90 km"},
                    {"title": "B28", "text": "Gemiddeld 28 km/u\n75 tot 85 km"},
                    {"title": "B25", "text": "Gemiddeld 25 km/u\n60 tot 70 km"},
                    {"title": "B22", "text": "Gemiddeld 22 km/u\n55 tot 65 km"},
                ]}),
                ("heading", "Wanneer en waar vertrekken we?"),
                ("paragraph",
                 "<p>Elke <b>zondagochtend</b> vertrekken de groepen aan de ingang van basisschool De Wijzer in "
                 "Zonnebeke, meestal om <b>8.15 uur</b> (tenzij anders vermeld in de nieuwsbrief of de clubkalender). "
                 "In de zomer rijden we ook op <b>woensdagavond</b>, met vertrek om 18.00 uur.</p>"
                 "<p>We rijden ritten die de club zelf uitstippelt, tochten van clubs uit de buurt en ook "
                 "(semi-)klassiekers.</p>"),
                ("heading", "Meer dan fietsen alleen"),
                ("paragraph",
                 "<p>Samen organiseren we elk jaar drie evenementen: de cyclotocht <b>WaCaCa</b> in april, de "
                 "<b>Zonneronde</b> in juni en de mountainbiketocht <b>Nonnebossentocht</b> in oktober. Daarnaast zijn "
                 "er het clubsouper, de clubreis en het clubfeest. Zo leer je ook de leden van de andere groepen "
                 "kennen.</p>"),
                ("callout", {
                    "title": "Zin om mee te rijden?",
                    "text": "<p>Kom gerust twee keer gratis proefrijden voor je lid wordt. Laat het ons vooraf even "
                    "weten, dan zorgen we dat je in de juiste groep terechtkomt.</p>",
                }),
            ),
        )
        root.add_child(instance=home)
        home.save_revision().publish()
        site = Site.objects.filter(is_default_site=True).first()
        if site:
            site.root_page = home
            site.site_name = "WTC Zonnebeke"
            site.save()
        else:
            Site.objects.create(hostname="localhost", root_page=home, is_default_site=True, site_name="WTC Zonnebeke")
        return home

    def lid_worden(self, home):
        return self.child(
            home, ContentPage, "Lid worden", "lid-worden",
            intro="Fiets je liever niet alleen? Word lid van WTC Zonnebeke en rij elke week mee met een groep op jouw niveau.",
            body=stream(
                ("heading", "Eerst proberen"),
                ("paragraph",
                 "<p>Twijfel je nog? Je mag twee testritten meerijden voor je beslist. Laat het vooraf weten aan een "
                 "bestuurslid of via het contactformulier. Voor de testritten heb je wel een verzekering burgerlijke "
                 "aansprakelijkheid (familiale verzekering) nodig.</p>"),
                ("heading", "Wat kost het?"),
                ("paragraph",
                 "<ul><li><b>Lidgeld: € 65 per jaar.</b> Daarin zit je VBR-verzekering (ongevallen en burgerlijke "
                 "aansprakelijkheid) en de werking van de club: het clubsouper, de clubreis en een aantal clubrally's.</li>"
                 "<li><b>Clubpakket voor nieuwe leden: € 180.</b> Zomertrui korte mouwen, trui lange mouwen, korte broek, "
                 "lange broek, body en een paar sokken van Bioracer, aan een sterk verminderde prijs.</li>"
                 "<li>Aansluiten of heraansluiten na 1 december kost € 10 extra.</li>"
                 "<li>Je gezinsleden kunnen gratis mee verzekerd worden.</li></ul>"),
                ("heading", "Goed om te weten"),
                ("paragraph",
                 "<p>Je moet in de loop van het seizoen minstens 14 jaar worden. Jongeren onder de 16 rijden mee onder "
                 "begeleiding van een volwassene. Alle afspraken staan in het clubreglement.</p>"),
                ("callout", {
                    "title": "Online inschrijven",
                    "text": "<p>Binnenkort schrijf je je hier online in en betaal je meteen met Bancontact. Tot dan "
                    "neem je contact op met het bestuur.</p>",
                }),
            ),
        )

    def events(self, home):
        index = self.child(
            home, EventIndexPage, "Evenementen", "evenementen",
            intro="Elk jaar organiseert WTC Zonnebeke tochten voor alle fietsers, ook voor wie geen lid is van de club.",
        )
        self.child(
            index, EventPage, "WaCaCa", "wacaca", show_in_menus=False,
            summary="Cyclotocht over de Wattenberg, de Casselberg en de Catsberg",
            intro="In april trekken we met de racefiets naar Frans-Vlaanderen. Drie heuvels, één onvergetelijke tocht.",
            body=stream(
                ("paragraph",
                 "<p>De naam zegt het al: <b>Wa</b>ttenberg, <b>Ca</b>sselberg en <b>Ca</b>tsberg. Deze drie heuvels in "
                 "Frans-Vlaanderen vormen het hart van onze voorjaarsklassieker. Onderweg fiets je door een glooiend "
                 "landschap met molens, kasseien en dorpjes waar de tijd lijkt stil te staan.</p>"
                 "<p>De WaCaCa is een toertocht, geen wedstrijd. Je rijdt op je eigen tempo, alleen of met vrienden, "
                 "en kiest de afstand die bij je past. Onderweg zorgen onze vrijwilligers voor bevoorrading en de "
                 "pijlen wijzen je de weg.</p>"),
                ("callout", {
                    "title": "Praktische info volgt",
                    "text": "<p>Datum, afstanden, startplaats en inschrijvingsprijs voor de volgende editie maken we "
                    "hier bekend.</p>",
                }),
            ),
        )
        self.child(
            index, EventPage, "Nonnebossentocht", "nonnebossentocht", show_in_menus=False,
            summary="Mountainbiketocht door de bossen en velden rond Zonnebeke",
            intro="Elk najaar nodigen we mountainbikers uit voor een tocht door het mooiste stukje natuur van Zonnebeke.",
            video_url="https://www.youtube.com/watch?v=rI-Dcwxhtbo",
            body=stream(
                ("paragraph",
                 "<p>De Nonnebossentocht is onze VTT-tocht in oktober. Je rijdt over bospaden, veldwegen en singletracks "
                 "door de Nonnebossen en de omgeving van Zonnebeke. Herfstkleuren, modder en een warme ontvangst na "
                 "afloop: meer heeft een mountainbiker niet nodig.</p>"
                 "<p>De tocht is er voor iedereen: voor de recreatieve biker die rustig van de natuur wil genieten en "
                 "voor wie graag wat sneller gaat. Je kiest zelf je afstand.</p>"),
                ("callout", {
                    "title": "Praktische info volgt",
                    "text": "<p>Datum, afstanden, startplaats en inschrijvingsprijs voor de volgende editie maken we "
                    "hier bekend.</p>",
                }),
            ),
        )
        return index

    def board(self, home):
        page = BoardPage.objects.first()
        if page:
            return page
        page = BoardPage(
            title="Bestuur", slug="bestuur", show_in_menus=True,
            intro="Deze negen vrijwilligers houden de club draaiende. Heb je een vraag? Ze helpen je graag verder.",
        )
        for order, (name, role, tasks) in enumerate(BOARD):
            page.members.add(BoardMember(sort_order=order, name=name, role=role, tasks="\n".join(tasks)))
        return self.publish(home, page)

    def rules(self, home):
        return self.child(
            home, RulesPage, "Clubreglement", "clubreglement",
            intro="De afspraken die het fietsen in onze club veilig en aangenaam houden.",
            version="januari 2026 (ontwerp, nog goed te keuren door het bestuur)",
            body=(SEED_DIR / "clubreglement.html").read_text(encoding="utf-8"),
        )

    def cyql(self, home):
        return self.child(
            home, CyqlPage, "Cyql-app", "cyql",
            intro="Onze club gebruikt de app Cyql voor de clubkalender en het klassement.",
            body=stream(
                ("paragraph",
                 "<p>In Cyql zie je welke ritten er gepland staan en hoe je ervoor staat in het klassement. "
                 "Zo heb je alle clubinfo altijd bij de hand op je gsm.</p>"),
                ("heading", "Zo begin je"),
                ("paragraph",
                 "<ol><li>Scan de QR-code of tik op de knop.</li>"
                 "<li>Installeer de app en maak een account aan.</li>"
                 "<li>Via de uitnodiging meld je je aan bij WTC Zonnebeke. Een bestuurslid keurt je "
                 "aanmelding goed.</li></ol>"),
            ),
        )

    def downloads(self, home, shop):
        page = DownloadsPage.objects.first()
        if page:
            return page
        page = self.publish(home, DownloadsPage(
            title="Downloads", slug="downloads", show_in_menus=True,
            intro="Formulieren en documenten voor leden, zoals de ongevalsaangifte.",
        ))
        # In het menu net voor de webshop.
        page.move(shop, pos="left")
        return DownloadsPage.objects.get(pk=page.pk)

    def contact(self, home):
        page = ContactPage.objects.first()
        if page:
            return page
        page = ContactPage(
            title="Contact", slug="contact", show_in_menus=True,
            intro="Vragen over de club, een testrit of onze evenementen? Laat een bericht achter, we antwoorden zo snel mogelijk.",
            to_address="info@wtczonnebeke.be",
            from_address="info@wtczonnebeke.be",
            subject="Bericht via het contactformulier",
        )
        fields = [
            ("Naam", "singleline", True, ""),
            ("E-mailadres", "email", True, ""),
            ("Gsm-nummer", "singleline", False, "Niet verplicht, handig als we je snel willen bellen."),
            ("Bericht", "multiline", True, ""),
        ]
        for order, (label, field_type, required, help_text) in enumerate(fields):
            page.form_fields.add(ContactFormField(
                sort_order=order, label=label, field_type=field_type, required=required, help_text=help_text,
                clean_name=get_field_clean_name(label),
            ))
        return self.publish(home, page)

    # Instellingen, sponsors en doorverwijzingen -------------------------------

    def settings(self):
        club = Clubgegevens.load()
        if not club.address:
            club.vzw_name = "WTC Zonnebeke vzw"
            club.address = "Roeselarestraat 81, 8980 Zonnebeke"
            club.enterprise_number = "BE 0878.308.274"
            club.rpr = "Gent, afdeling Ieper"
            club.iban = "BE41 7330 3307 5010"
            club.email = "info@wtc-zonnebeke.be"
            club.phone = "0475 60 82 00"
            club.meeting_place = "Ingang basisschool De Wijzer, Zonnebeke"
            club.facebook_url = "https://www.facebook.com/zonnebeke/"
            club.strava_url = "https://www.strava.com/clubs/107957/"
            club.privacy_url = "https://wtc-zonnebeke.be/vzw/privacyverklaring.pdf"
            club.save()
        statuten = Statuten.load()
        if not statuten.url:
            statuten.url = "https://wtc-zonnebeke.be/vzw/statuten_2026.pdf"
            statuten.save()
        CyqlApp.load().save()
        # Tenant-ID en e-mailadressen komen uit de omgeving: de repository is openbaar.
        Integraties.load().save()
        toegang = Toegang.load()
        if not toegang.admin_emails and not toegang.stock_emails:
            toegang.admin_emails = "\n".join(settings.BOOTSTRAP_ADMIN_EMAILS)
            toegang.stock_emails = "\n".join(
                e.strip() for e in os.environ.get("SEED_STOCK_EMAILS", "").split(",") if e.strip()
            )
            toegang.save()
        qr = QrInfo.load()
        if not qr.event_date:
            qr.event_date = datetime.date(2026, 4, 11)
            qr.save()

    def sponsors(self):
        for order, (name, url) in enumerate(SPONSORS):
            Sponsor.objects.get_or_create(name=name, defaults={"url": url, "is_main": True, "sort_order": order})

    def redirects(self, pages):
        for old_path, key in LEGACY_REDIRECTS.items():
            normalised = Redirect.normalise_path(old_path)
            if not Redirect.objects.filter(old_path=normalised).exists():
                Redirect.add_redirect(old_path, redirect_to=pages[key], is_permanent=True)

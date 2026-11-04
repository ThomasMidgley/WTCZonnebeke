# Technische referentie website WTC Zonnebeke

_Kopie van de online versie, bijgewerkt op 2 november 2026._

## Overzicht en architectuur

De hele website is één Docker-container op de Raspberry Pi. Er staat geen poort open: bezoekers komen binnen via een Cloudflare Tunnel. Geheimen staan enkel als omgevingsvariabelen in de Portainer-stack, nooit in Git of in de database.

```
Bezoeker ──https──> Cloudflare (DNS + tunnel) ──> cloudflared (container op de Pi)
                                                     │  Docker-netwerk "tunnel"
                                                     ▼
                                   wtc-website:8000 (Gunicorn + Django/Wagtail)
                                                     │
                                   volume wtc-data (/data): db.sqlite3, media/, backups/

wtc-website ──> Microsoft 365 (aanmelden beheer + mail versturen via Graph)
            ──> Stripe (betalen) <── webhook /stripe/webhook/
            ──> Cyql API (nachtelijke sync: kalender, klassement, leden)
            ──> Cloudflare Turnstile (optioneel, captcha op formulieren)
```

| Onderdeel | Keuze |
| --- | --- |
| Code | Python 3.13, Django 5.2, Wagtail 7.4, gewone CSS, nauwelijks JavaScript |
| Database | SQLite in /data/db.sqlite3 |
| Webserver | Gunicorn (2 workers, 2 threads), statische bestanden via WhiteNoise |
| Hosting | Raspberry Pi (arm64), Portainer, container wtc-website |
| Bron | GitHub: ThomasMidgley/WTCZonnebeke (publiek) |
| Image | ghcr.io/thomasmidgley/wtczonnebeke:main |

### Wat gebeurt er bij elke start van de container

1. `migrate`: de database wordt bijgewerkt naar de nieuwste versie.
2. `seed_site`: maakt startinhoud aan die nog niet bestaat (pagina's, instellingen, webshop, lidgeld). Bestaande inhoud blijft staan.
3. Een lus die elke nacht om BACKUP\_TIME (02:30) `backup_db` draait.
4. `run_scheduler`: de Cyql-sync op het uur uit Cyql > Instellingen, en het opruimen van onbetaalde bestellingen.
5. Gunicorn op poort 8000. De healthcheck vraagt elke minuut /gezond/ op.

### Repository in het kort

| Map | Inhoud |
| --- | --- |
| config/ | settings.py (alle omgevingsvariabelen), urls.py |
| apps/core | Instellingen, sponsors, QR-pagina, mail via Graph, back-up, seed\_site |
| apps/pages | Paginatypes (home, bestuur, evenement, contact ...) |
| apps/accounts | Aanmelden met Microsoft 365, rollen beheerder en stockbeheerder |
| apps/cyql | Cyql-koppeling, sync, planner |
| apps/shop | Webshop, Stripe, stock-app (/stock/) |
| apps/formulieren | Formulierenbouwer (/formulier/\<code>/). herinschrijving.py vergelijkt de lidgeldlijst met de Cyql-leden (exports Import Cyql en Inactieve leden). De Cyql-API kan enkel lezen: leden toevoegen, uitschakelen of verwijderen gebeurt in Cyql zelf. |
| apps/mails | Alle uitgaande mails: MailTemplate (onderwerp en teksten, aanpasbaar in de admin onder E-mails), registry.py (welke mails er zijn, wanneer en naar wie), MailLog (90 dagen, opnieuw versturen). Vaste middenstukken in templates/mails/body/. |
| seed/ | Startinhoud: clubreglement, bijlagen, productfoto's |
| README.md | Installatie in het kort; deze referentie is de uitgebreide versie |
| docs/ | Kopie van de handleiding beheer en van deze technische referentie, bijgewerkt bij elke wijziging. |

## GitHub en het Docker-image

De code staat in de publieke repository **github.com/ThomasMidgley/WTCZonnebeke**. Omdat ze publiek is, staat er niets geheims in: geen sleutels, tenant-ID's, e-mailadressen of club-ID's. Die horen in de stack of in de beheeromgeving.

### Automatisch bouwen

De workflow *.github/workflows/docker.yml* draait bij elke push en pull request:

1. **test**: `makemigrations --check` en `python manage.py test apps` (met DEBUG=1).
2. **build**: bouwt het image voor linux/arm64 (de Pi) en linux/amd64 en zet het op GitHub Packages (ghcr.io). Enkel bij een push naar main of een tag, niet bij een pull request.

| Tag | Wanneer |
| --- | --- |
| main | Laatste versie van de branch main. Die gebruikt de stack standaard. |
| v1.2.3 | Bij een Git-tag v1.2.3. Handig om vast te pinnen. |
| korte commit-hash | Elke build; om exact terug te keren naar een versie. |

Een nieuwe versie live zetten: pull request mergen naar main, wachten tot de actie **Docker-image bouwen** groen is (ongeveer 10 minuten door de arm64-build), dan in Portainer redeployen (zie verder).

### Terug naar een vorige versie

Zet in de stack `IMAGE_TAG` op de korte hash of tag van de vorige build (te vinden onder *Actions* of *Packages* in GitHub) en redeploy. Let op: een nieuwere databaseversie (migratie) gaat niet vanzelf terug. Is er een migratie bijgekomen, zet dan ook de back-up van voor de update terug.

### Toegang

- De Claude GitHub App moet geïnstalleerd zijn op de repository om wijzigingen te pushen.
- Is het image ooit privé, voeg dan in Portainer onder *Registries* ghcr.io toe met je GitHub-gebruikersnaam en een personal access token met enkel `read:packages`.

### Lokaal ontwikkelen

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DEBUG=1
python manage.py migrate && python manage.py seed_site
python manage.py runserver
python manage.py test apps
```

## Raspberry Pi, Portainer en omgevingsvariabelen

### De stack aanmaken

1. Portainer > *Stacks* > *Add stack*, naam bv. `wtc-website`.
2. Kies *Repository*: URL `https://github.com/ThomasMidgley/WTCZonnebeke`, referentie `refs/heads/main`, compose-pad `docker-compose.yml`. (Of plak de inhoud van docker-compose.yml in de *Web editor*.)
3. Vul onder *Environment variables* de variabelen hieronder in.
4. *Deploy the stack*. De eerste start maakt de database en alle startinhoud; dat duurt een minuut.

De container heet **wtc-website**, hangt aan het bestaande Docker-netwerk **tunnel** (waar cloudflared ook in zit) en bewaart alles in het volume **wtc-data**.

### Een update binnenhalen

Stack openen > *Pull and redeploy* (of *Update the stack*) en zet **Re-pull image** aan. Zonder die schakelaar start Portainer gewoon de oude versie opnieuw.

### Omgevingsvariabelen

Geen enkele waarde hieronder hoort in Git, in de chat of in een document. Bewaar de geheimen in een wachtwoordkluis.

| Variabele | Waarvoor | Waar haal je de waarde |
| --- | --- | --- |
| SECRET\_KEY | Ondertekening sessies en CSRF. Verplicht. | Zelf maken: `python -c "import secrets; print(secrets.token_urlsafe(50))"`. Wijzigen meldt iedereen af. |
| ALLOWED\_HOSTS | Domeinen die de site aanvaardt | Nu: wtczonnebeke.be,www.wtczonnebeke.be. Na livegang ook wtc-zonnebeke.be en www.wtc-zonnebeke.be. |
| CSRF\_TRUSTED\_ORIGINS | Idem, met https:// ervoor | Zelfde domeinen, bv. https://www.wtczonnebeke.be |
| BASE\_URL | Adres in mails, links en Stripe-terugkeer | https://www.wtczonnebeke.be (na livegang het nieuwe domein) |
| SITE\_NOINDEX | 1 = zoekmachines weren | 1 tijdens de test, 0 bij livegang |
| AZURE\_TENANT\_ID | Microsoft 365-tenant | Entra admin center > Overview > Tenant ID |
| AZURE\_CLIENT\_ID | App-registratie WTC Website | Entra > App registrations > WTC Website > Application (client) ID |
| AZURE\_CLIENT\_SECRET | Geheim van die app | Entra > WTC Website > Certificates & secrets (de *Value*, maar één keer zichtbaar) |
| BOOTSTRAP\_ADMIN\_EMAILS | Wie altijd beheerder is, ook als Instellingen > Toegang leeg is | Het info@-adres van de club, komma's ertussen |
| SEED\_STOCK\_EMAILS | Startwaarde voor stockbeheerders (enkel bij de eerste start) | Mailadres(sen) van de stockbeheerder |
| ALLOW\_PASSWORD\_LOGIN | Noodtoegang zonder Microsoft | Altijd 0, enkel 1 in nood |
| CYQL\_API\_KEY | Cyql-koppeling | Cyql-dashboard > Settings > API |
| STRIPE\_SECRET\_KEY | Betalingen | Stripe > Ontwikkelaars > API-sleutels (sk\_test\_... of sk\_live\_...) |
| STRIPE\_WEBHOOK\_SECRET | Webhook controleren | Stripe > Ontwikkelaars > Webhooks > eindpunt > Ondertekeningsgeheim (whsec\_...) |
| TURNSTILE\_SITE\_KEY, TURNSTILE\_SECRET\_KEY | Optionele captcha op formulieren | Cloudflare > Turnstile (zie verder) |
| TUNNEL\_NETWORK | Naam van het Docker-netwerk van cloudflared | Standaard tunnel |
| BACKUP\_TIME | Uur van de nachtelijke back-up | Standaard 02:30 |
| GUNICORN\_WORKERS | Aantal processen | Standaard 2; meer is niet nodig op een Pi |
| IMAGE\_TAG | Welke versie draait | Standaard main |

Na het wijzigen van een variabele: *Update the stack*. De container herstart en neemt de nieuwe waarde.

### Handige consolecommando's

Portainer > *Containers* > wtc-website > *Console* > Connect (/bin/sh):

| Commando | Wat |
| --- | --- |
| `python manage.py backup_db` | Nu een back-up maken |
| `python manage.py cyql_sync` | Nu Cyql synchroniseren |
| `python manage.py createsuperuser` | Noodgebruiker (enkel met ALLOW\_PASSWORD\_LOGIN=1) |
| `python manage.py seed_site` | Ontbrekende startinhoud aanmaken (wijzigt niets bestaands) |
| `python manage.py cyql_schema` | **Niet gebruiken** tenzij nodig: kost veel Cyql-budget |

## Cloudflare: DNS en tunnel

De domeinen staan in Cloudflare. Het verkeer loopt via een bestaande **Cloudflare Tunnel**: de container cloudflared op de Pi bouwt zelf een verbinding naar Cloudflare op, dus er moet geen poort open in de router.

### Tunnel en public hostnames

Cloudflare-dashboard > *Zero Trust* > *Networks* > *Tunnels* > de bestaande tunnel > *Public hostnames* (in nieuwere versies *Published application routes*) > *Add*:

| Subdomain | Domain | Service |
| --- | --- | --- |
| www | wtczonnebeke.be | HTTP, wtc-website:8000 |
| (leeg) | wtczonnebeke.be | HTTP, wtc-website:8000 |
| www | wtc-zonnebeke.be | HTTP, wtc-website:8000 (bij livegang) |
| (leeg) | wtc-zonnebeke.be | HTTP, wtc-website:8000 (bij livegang) |

Cloudflare maakt daarbij zelf de DNS-records aan (een CNAME naar `<tunnel-id>.cfargotunnel.com`). Bestaat er al een A- of CNAME-record voor die naam (bv. naar de oude hosting), verwijder dat dan eerst in *DNS* > *Records*, anders weigert Cloudflare de hostname.

De naam **wtc-website** werkt enkel omdat cloudflared en de website in hetzelfde Docker-netwerk **tunnel** zitten. Zit cloudflared in een ander netwerk, zet dan TUNNEL\_NETWORK op die naam.

### Instellingen in de zone

- *SSL/TLS* > modus **Full** (of Flexible); de tunnel regelt de versleuteling. *Always Use HTTPS* aan.
- Geen caching-regels nodig voor /admin, /stock of /stripe: Cloudflare cachet standaard geen HTML.
- Geen Rocket Loader of andere scriptinjectie: die botst met de Content-Security-Policy.

### Optioneel: Cloudflare Access voor /admin

*Zero Trust* > *Access* > *Applications* > *Add* > *Self-hosted*, domein www.wtczonnebeke.be, pad `admin`, login via Microsoft Entra ID, beleid: e-mail eindigt op het clubdomein. Dan ziet niemand buiten de club zelfs het aanmeldscherm. Doe dit **niet** voor /stripe/webhook/ (Stripe moet daar zonder login bij) en test daarna of de stock-app op de gsm nog werkt.

### Mail-DNS (bij livegang)

De website mailt via Microsoft 365 (Graph) vanaf het info@-adres, dus SPF, DKIM en DMARC van het **maildomein** moeten in orde zijn:

| Record | Waarde (voorbeeld) |
| --- | --- |
| TXT @ (SPF) | `v=spf1 include:spf.protection.outlook.com -all` |
| CNAME selector1.\_domainkey en selector2.\_domainkey (DKIM) | De twee waarden uit Microsoft Defender > *Email authentication settings* > DKIM; daarna DKIM inschakelen |
| TXT \_dmarc (DMARC) | Begin met `v=DMARC1; p=none; rua=mailto:<adres>`, na een paar weken zonder problemen `p=quarantine` |
| MX @ | Zoals Microsoft 365 aangeeft (\*.mail.protection.outlook.com) |

## Microsoft 365-tenant

Microsoft 365 doet twee dingen voor de website: **aanmelden** in de beheeromgeving en de stock-app (SSO), en **mails versturen** (bevestigingen, meldingen) via Microsoft Graph vanaf het info@-adres. Beide lopen via één app-registratie: **WTC Website**.

### App-registratie maken

1. entra.microsoft.com > *Identity* > *Applications* > *App registrations* > *New registration*.
2. Naam `WTC Website`, *Accounts in this organizational directory only* (single tenant).
3. Redirect URI: platform *Web*, `https://www.wtczonnebeke.be/admin/login/callback/`. Bij de livegang voeg je onder *Authentication* toe: `https://www.wtc-zonnebeke.be/admin/login/callback/` (en eventueel zonder www). Een ontbrekende redirect URI geeft fout AADSTS50011.
4. Kopieer van *Overview*: **Application (client) ID** naar AZURE\_CLIENT\_ID en **Directory (tenant) ID** naar AZURE\_TENANT\_ID.
5. *Certificates & secrets* > *New client secret*, looptijd 24 maanden. Kopieer de **Value** (niet de Secret ID) naar AZURE\_CLIENT\_SECRET. Zet een herinnering in je agenda een maand voor de vervaldatum: is het geheim verlopen, dan werken aanmelden en mails niet meer.

### Rechten (API permissions)

| Recht | Soort | Waarvoor |
| --- | --- | --- |
| openid, profile, email, User.Read | Delegated | Aanmelden |
| Mail.Send | Application | Mails versturen zonder dat iemand aangemeld is |
| GroupMember.Read.All | Application | De ledengroep opzoeken |
| User.Read.All | Application | De e-mailadressen van de leden in de ledengroep lezen |
| User.Invite.All | Application | Leden als gast in de tenant zetten voor de ledengroep (zonder uitnodigingsmail) |
| GroupMember.ReadWrite.All | Application | Leden toevoegen aan en verwijderen uit de ledengroep |

Klik na het toevoegen op **Grant admin consent**. Zonder beperking mag de app met Mail.Send als **elke** mailbox mailen. Beperk dat tot het info@-adres via Exchange Online PowerShell:

```
Connect-ExchangeOnline
New-ApplicationAccessPolicy -AppId <client-id> -PolicyScopeGroupId <info@-adres> -AccessRight RestrictAccess -Description "WTC Website mag enkel als info@ mailen"
Test-ApplicationAccessPolicy -AppId <client-id> -Identity <info@-adres>
```

Het afzenderadres stel je in de beheeromgeving in: Instellingen > Integraties > mail\_sender (afzender). Tenant- en client-ID kunnen daar ook, maar de omgevingsvariabelen hebben voorrang.

### Ledengroep

De website houdt een Microsoft 365-groep (bv. leden@wtczonnebeke.be) gelijk met de goedgekeurde Cyql-leden. Leden komen als gast in de tenant zonder uitnodigingsmail; enkel gasten worden toegevoegd of verwijderd. Een verwijderd lid blijft gast in de tenant, maar zit niet meer in de groep (opruimen kan in Entra > *Users*, filter *Guest*). Code: `apps/cyql/member_group.py`.

Eenmalig instellen:

1. Microsoft 365-beheercentrum > *Teams & groups* > *Active teams & groups* > *Add a group* > **Microsoft 365**. Naam bv. "Leden WTC Zonnebeke", adres leden@, privacy *Private*, geen Team aanmaken. Eigenaar: info@.
2. Bij de groep > *Settings*: **Allow external senders to email this group** uit, **Send copies of group conversations and events to group members' inboxes** aan.
3. *Settings* > *Org settings* > *Microsoft 365 Groups*: **Let group owners add people outside your organization** aan. In Entra > *External Identities* > *External collaboration settings* mag het uitnodigen van gasten niet volledig uit staan.
4. App-registratie: de rechten GroupMember.Read.All, User.Read.All, User.Invite.All en GroupMember.ReadWrite.All toevoegen (zie hierboven) en **Grant admin consent for ...** (globale beheerder; geldt enkel voor deze app). Pas als er overal "Granted" staat, werkt het.
5. Beheeromgeving > **Cyql** > *Instellingen* > *Ledengroep*: het adres van de groep, en bij *Enkel deze adressen (test)* eerst 2 of 3 eigen adressen. *Nu synchroniseren*, het verslag nakijken en een testmail sturen naar de groep vanuit Outlook.
6. Komt de testmail aan, maak het testveld leeg. De volgende sync zet alle leden in de groep.
7. Welkomstmail ("You've joined the ... group") uitschakelen. Dat kan niet in het admin center, enkel in Exchange Online PowerShell, eenmalig per groep (geldt voor de groep, niet voor het domein):
   - Windows: startmenu, "PowerShell", rechtermuisknop, *Als administrator uitvoeren*.
   - `Install-Module ExchangeOnlineManagement` (eenmalig; melding over scripts: eerst `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`).
   - `Connect-ExchangeOnline -UserPrincipalName info@wtczonnebeke.be` (aanmeldvenster van Microsoft, globale beheerder).
   - `Set-UnifiedGroup -Identity leden@wtczonnebeke.be -UnifiedGroupWelcomeMessageEnabled:$false`

Testen zonder Cyql-budget, in de console van de container (Portainer > container > *Console* > `/bin/sh`):

```
python manage.py ledengroep              # controle: rechten in het token, groep, wat er zou gebeuren; wijzigt niets
python manage.py ledengroep --uitvoeren  # de groep echt bijwerken met de ledenlijst die al in de database staat
```

De controle toont welke rechten Microsoft echt aan de app geeft. Staat een recht in Entra maar niet in het token, dan is het meestal als *Delegated* in plaats van *Application* toegevoegd, of ontbreekt de admin consent nog.

Los van de website kan het ook met `scripts/ledengroep_test.py` (enkel Python 3, geen extra pakketten). Het vraagt tenant-ID, client-ID en geheim (of leest AZURE\_TENANT\_ID, AZURE\_CLIENT\_ID en AZURE\_CLIENT\_SECRET), toont de rechten in het token, zoekt de groep op en toont de leden. Met `--test-adres iemand@voorbeeld.be --uitvoeren` voegt het één adres als gast toe aan de groep.

```
python ledengroep_test.py leden@wtczonnebeke.be
python ledengroep_test.py leden@wtczonnebeke.be --test-adres iemand@gmail.com --uitvoeren
```

Beveiligingen: de groep wordt enkel bijgewerkt met een ledenlijst die bij dezelfde sync gelukt is; een lege lijst verwijdert niemand en meer dan de helft in één keer evenmin. In de beheerpagina stopt het toevoegen na 30 seconden (Gunicorn-limiet), 's nachts is er geen limiet. Foutmelding 403 in het verslag betekent dat een recht of de admin consent ontbreekt; het verslag zegt bij welke stap (groep opzoeken, groepsleden lezen, gast aanmaken, toevoegen). Leden van wie de app het adres niet kan lezen, worden nooit uit de groep gehaald. GroupMember.ReadWrite.All geldt technisch voor alle groepen van de tenant; Microsoft laat geen beperking tot één groep toe. De website raakt enkel de ingestelde groep aan, en daarin enkel gasten.

### Wie mag binnen

- Iedereen in BOOTSTRAP\_ADMIN\_EMAILS is altijd beheerder (vangnet).
- Andere beheerders en stockbeheerders: Instellingen > Toegang, één adres per lijn.
- Wie zich aanmeldt maar op geen lijst staat, krijgt een melding dat hij of zij geen toegang heeft.

### MFA

Tijdens de opbouw stond MFA uit voor het info@-account. **Bij de livegang terug aanzetten** (Entra > *Security* > *Authentication methods* of de *Security defaults*). De website zelf heeft geen MFA nodig: die laat het aanmelden over aan Microsoft.

### Noodtoegang

Werkt Microsoft-aanmelden niet (verlopen geheim, storing): zet ALLOW\_PASSWORD\_LOGIN=1 in de stack, open de console en voer `python manage.py createsuperuser` uit. Meld je aan op /admin/login/ met gebruikersnaam en wachtwoord. Zet het daarna meteen terug op 0.

## Stripe

Stripe verwerkt de betalingen van de webshop (Stripe Checkout). De website bewaart geen kaartgegevens; de klant betaalt op een pagina van Stripe en komt daarna terug.

### Account en instellingen

1. dashboard.stripe.com, account op naam van de vzw, met het IBAN van de club voor uitbetalingen.
2. *Instellingen* > *Betaalmethodes*: Bancontact, kaarten, Apple Pay en Google Pay aan.
3. *Instellingen* > *Openbare gegevens*: afschriftomschrijving `WTC ZONNEBEKE`, e-mail en website van de club.
4. Geen btw instellen: de vzw is niet btw-plichtig.

### Sleutels

*Ontwikkelaars* > *API-sleutels*. Enkel de **geheime sleutel** is nodig, als STRIPE\_SECRET\_KEY in de stack. De publieke sleutel (pk\_...) mag in Instellingen > Integraties maar wordt niet strikt gebruikt.

Test en live zijn twee aparte werelden met elk hun eigen sleutels **en** hun eigen webhook. Bij de overstap naar live vervang je dus beide geheimen.

### Webhook

De webhook vertelt de website dat er betaald is. Zonder werkende webhook blijft een bestelling op *Aan het afrekenen* staan.

1. *Ontwikkelaars* > *Webhooks* > *Eindpunt toevoegen* (in nieuwere versies *Workbench* > *Webhooks* > *Create an event destination*).
2. URL: `https://www.wtczonnebeke.be/stripe/webhook/`. **De slash op het einde is verplicht**; zonder krijgt Stripe een 301 en faalt elke levering. Na de livegang: het nieuwe domein.
3. Payload-stijl: **snapshot**.
4. Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`.
5. Kopieer het **ondertekeningsgeheim** (whsec\_...) naar STRIPE\_WEBHOOK\_SECRET en update de stack.

Controle: doe een testbestelling en kijk bij het eindpunt naar *Gebeurtenissen*. Elke levering moet 200 geven. Een 400 betekent meestal een verkeerd whsec-geheim, een 301 een ontbrekende slash.

### Testen

Met sk\_test\_: testkaart `4242 4242 4242 4242`, een datum in de toekomst, CVC 123. Bancontact in testmodus laat je kiezen tussen slagen en mislukken.

### Wat de website met een betaling doet

- Bij betaling: bestelling op *Betaald*, mails naar klant en stockbeheerder. Een bestelling met enkel events of lidgeld gaat meteen naar *Geleverd*.
- Bij een event met formulier: de antwoorden komen ook bij Formulieren > antwoorden.
- Bij lidgeld: het nieuwe lid krijgt de Cyql-uitnodigingslink.
- Niet betaald binnen 30 minuten: *Verlopen*, de reservatie vervalt.

Terugbetalingen doe je in het Stripe-dashboard bij de betaling (*Terugbetalen*); de website past de status niet vanzelf aan.

## Webshop: artikelcategorieën (november 2026)

Een artikel heeft een categorie (Algemeen, Dames, Heren) en één artikelnummer; een maat heeft geen heren/dames meer. Migratie `shop/0008` splitste elk artikel met heren- én damesmaten: het bestaande artikel werd het herenartikel, de damesmaten verhuisden naar een nieuw artikel met adres `...-dames`. Stock, logboek en oude bestellingen bleven bij dezelfde maten. Een pakket met gesplitste onderdelen werd "... heren" en kreeg een kopie "... dames" (adres `clubpakket-dames`) met de damesartikels. Het thermisch fietsshirt werd verwijderd (fout in de stocklijst; verborgen in plaats van verwijderd als er al bestellingen voor waren). Terugdraaien naar een oudere versie gaat niet zonder een back-up van vóór de update.

## Cyql

Cyql is de club-app waarin leden, ritten en klassementen beheerd worden. De website leest Cyql alleen; ze schrijft er nooit naar.

### Koppeling instellen

1. dashboard.cyql.app > *Settings* > *API* > *New API key*. Kopieer de sleutel meteen; je ziet hem maar één keer.
2. Zet hem als CYQL\_API\_KEY in de stack en update de stack. Bewaar hem nergens anders dan in je wachtwoordkluis.
3. Beheeromgeving > **Cyql** > *Instellingen*: uur van de nachtelijke sync, de uitnodigingslink voor de app (komt in de welkomstmail bij lidgeld) en het linkformaat naar een activiteit.
4. *Cyql* > *Nu synchroniseren* voor een eerste test. Het verslag staat bij *Synchronisaties*.

### Wat er gesynchroniseerd wordt

| Gegeven | Gebruikt voor |
| --- | --- |
| Komende ritten en activiteiten, met GPX | Clubkalender en de volgende ritten op de home |
| Klassementen die op *tonen* staan | Pagina Klassement |
| Goedgekeurde leden (e-mailadres) | Lidcontrole in de webshop (ledenprijs, artikels enkel voor leden) |
| Goedgekeurde leden (naam, e-mailadres) | Ledengroep in Microsoft 365 (zie *Microsoft 365-tenant* > *Ledengroep*) |

Bezoekers zien enkel wat in de eigen database staat; een paginabezoek vraagt nooit iets aan Cyql.

### Budget

Cyql rekent per vraag een "complexiteit". Het plan van de club laat toe:

| Limiet | Waarde |
| --- | --- |
| Diepte per vraag | max. 5 |
| Complexiteit per vraag | max. 200 |
| Per week (reset maandag) | 5.000 |

Een sync kost ongeveer 300 met één getoond klassement; elk extra getoond klassement kost meer. Met één sync per nacht blijft de club ruim binnen het weekbudget, maar druk niet tientallen keren op *Nu synchroniseren*. Het commando `cyql_schema` vraagt het hele schema op en is **duur**: enkel gebruiken als de API verandert en er budget over is.

### Sleutel vervangen

Nieuwe sleutel maken in Cyql, in de stack zetten, stack updaten, *Nu synchroniseren* testen, daarna de oude sleutel intrekken in Cyql.

## Turnstile en andere integraties

### Cloudflare Turnstile (optioneel)

Een captcha op de openbare formulieren (/formulier/...). Zonder Turnstile houdt een onzichtbaar valstrikveld de meeste spambots al tegen; zet Turnstile pas aan als er toch spam binnenkomt.

1. Cloudflare-dashboard > *Turnstile* > *Add widget*.
2. Naam `WTC formulieren`, hostnames wtczonnebeke.be en www.wtczonnebeke.be (bij livegang ook wtc-zonnebeke.be), modus *Managed*.
3. Zet de **site key** in TURNSTILE\_SITE\_KEY en de **secret key** in TURNSTILE\_SECRET\_KEY, en update de stack.
4. Test een formulier: onderaan verschijnt het Cloudflare-vakje.

De website past de Content-Security-Policy enkel op formulierpagina's aan zodat challenges.cloudflare.com mag laden, en op de pagina Cyql-app als er een widgetcode is ingesteld (scripts, frames en verbindingen naar *.cyql.app, afbeeldingen en lettertypes via https). De rest van de site laadt geen externe scripts.

### Cyql-widget

De widgetcode (Cyql > Instellingen) wordt nooit zelf uitgevoerd. De website haalt de zeven waarden uit de code (element, club-ID, taal, hoogte, soort, ...), controleert ze en bouwt zelf het adres `https://dashboard.cyql.app/widgets/cw.js?...` op. Het script laadt pas na een klik op de knop (`static/js/site.js`). Toont de widget niets, kijk dan in de console van de browser naar CSP-meldingen: Cyql laadt misschien iets van een ander domein, dat dan aan `CYQL_WIDGET_CSP` in `apps/pages/models.py` moet worden toegevoegd.

### YouTube

Filmpjes laden pas na een klik (geen cookies of tracking vooraf). Er is geen sleutel of instelling nodig: je plakt de YouTube-link in een pagina.

### Instellingen in de beheeromgeving

Niet-geheime instellingen staan in Wagtail, onder **Instellingen**, en zitten dus in de database (en in de back-up):

| Instelling | Inhoud |
| --- | --- |
| Huisstijl | Basis- en accentkleur en logo (bewaard in /data/media/huisstijl/). De tekstkleur op de basiskleur wordt automatisch wit of zwart. Een SVG met scripts wordt geweigerd. |
| Clubgegevens | Naam vzw, adres, ondernemingsnummer, IBAN, e-mail, telefoon |
| Clubreglement, Vzw-statuten | Teksten |
| Integraties | Azure tenant- en client-ID (env heeft voorrang), afzender mails, Stripe publieke sleutel |
| Toegang | Beheerders en stockbeheerders (e-mailadressen) |
| QR-info pijltjes | Inhoud van /index.php?id=900 (adres in de QR-codes, **nooit wijzigen**) |
| Cyql (menu Cyql > Instellingen) | Uur van de sync, uitnodigingslink, linkformaat activiteit |

Sponsors beheer je in het menu **Sponsors**.

## Back-up, herstel en alles opnieuw opzetten

### Wat er bewaard moet worden

Alles wat niet in Git staat, zit op twee plaatsen:

| Wat | Waar | Hoe bewaren |
| --- | --- | --- |
| Database (pagina's, instellingen, bestellingen, formulieren, leden uit Cyql) | /data/db.sqlite3 in volume wtc-data | Nachtelijke back-up |
| Foto's en pdf's die beheerders opladen | /data/media | Nachtelijke back-up |
| Geheimen (omgevingsvariabelen) | Portainer-stack | **Jouw wachtwoordkluis**: noteer er elke waarde |

### Automatische back-up

Elke nacht om 02:30 maakt de container in /data/backups:

- `db-JJJJMMDD-UUMMSS.sqlite3`: een consistente kopie van de database, ook terwijl de site draait.
- `media-JJJJMMDD-UUMMSS.tar.gz`: alle opgeladen bestanden.

Back-ups ouder dan 30 dagen worden opgeruimd. Die back-ups staan wel op **dezelfde Pi**: neem het volume mee in de back-up van de Pi of kopieer /data/backups geregeld naar een andere plek (NAS, OneDrive). Op de Pi vind je het volume onder `/var/lib/docker/volumes/<stacknaam>_wtc-data/_data/` (controleer de naam met `docker volume ls`).

Een back-up op aanvraag, bv. voor een grote update: console > `python manage.py backup_db`.

### Een back-up terugzetten

1. Portainer > container wtc-website > **Stop**.
2. Op de Pi (ssh), in de map van het volume:

```
cd /var/lib/docker/volumes/<stacknaam>_wtc-data/_data
cp db.sqlite3 db.sqlite3.voor-herstel
cp backups/db-<datum>.sqlite3 db.sqlite3
rm -f db.sqlite3-wal db.sqlite3-shm
tar -xzf backups/media-<datum>.tar.gz   # enkel als ook foto's terug moeten
chown -R 1000:1000 .
```

3. Container **Start**. Kijk in de logs of `migrate` en `seed_site` zonder fouten lopen.

Bestellingen en betalingen die na het tijdstip van de back-up binnenkwamen, zijn dan weg uit de website (maar staan nog in Stripe).

### Alles opnieuw opzetten (nieuwe Pi of na een crash)

Volgorde, met verwijzing naar de hoofdstukken hierboven:

1. **Pi**: Raspberry Pi OS 64-bit, Docker en Portainer installeren.
2. **cloudflared**: tunnel-container opnieuw starten met het tunneltoken (Cloudflare > Zero Trust > Tunnels > de tunnel > *Configure* toont het installatiecommando met token), in het Docker-netwerk `tunnel` (`docker network create tunnel` als het nog niet bestaat).
3. **Stack** aanmaken in Portainer met alle omgevingsvariabelen uit je kluis (hoofdstuk Raspberry Pi). Gebruik dezelfde SECRET\_KEY als vroeger, anders is iedereen afgemeld (geen ramp).
4. Eerste start maakt een lege site met startinhoud. **Stop** de container meteen en zet de laatste back-up terug (zie hierboven), dan weer starten.
5. **Cloudflare**: public hostnames controleren (hoofdstuk Cloudflare). Werkt de site, dan is DNS in orde.
6. **Microsoft 365**: aanmelden testen op /admin/. Is het client secret ondertussen verlopen, maak een nieuw en update de stack.
7. **Stripe**: webhook-eindpunt ongewijzigd laten als het domein hetzelfde blijft; controleer bij *Gebeurtenissen* of leveringen weer 200 geven. Mislukte leveringen kun je daar opnieuw versturen.
8. **Cyql**: *Nu synchroniseren* en het verslag nakijken.
9. Een testbestelling met een product van €0,50 of in testmodus, en een formulier invullen.

Geen back-up meer? Dan start de site met de startinhoud van seed\_site (clubreglement, standaardpagina's, webshop met fictieve stock). Teksten, foto's, bestellingen en formulieren moet je dan opnieuw invoeren; de leden komen vanzelf terug uit Cyql.

## Updates en problemen oplossen

### Een update uitrollen

1. Pull request mergen naar main op GitHub.
2. Wachten tot de actie **Docker-image bouwen** groen is.
3. Bij een grote wijziging eerst `python manage.py backup_db` in de console.
4. Portainer > stack > *Pull and redeploy* met **Re-pull image** aan.
5. Logs bekijken: `migrate` en `seed_site` moeten zonder fout lopen, daarna start Gunicorn ("Booting worker").
6. Site openen en een snelle test: home, webshop, /admin/.

### Logs bekijken

Portainer > *Containers* > wtc-website > *Logs*. Elke foutmelding van Python staat daar met een "Traceback". Zet *Auto-refresh* aan en herhaal de fout in de browser.

### Gekende problemen en oplossingen

| Symptoom | Oorzaak | Oplossing |
| --- | --- | --- |
| Container blijft *unhealthy* of herstart steeds | Fout bij het opstarten, vaak een ontbrekende of foute variabele (SECRET\_KEY leeg) of een mislukte migratie | Logs lezen; variabele invullen; bij een mislukte migratie de back-up terugzetten en de vorige IMAGE\_TAG gebruiken |
| Nieuwe versie is niet zichtbaar na redeploy | *Re-pull image* stond uit, of de build op GitHub was nog bezig of mislukt | Actie op GitHub nakijken, opnieuw redeployen met Re-pull aan |
| Cloudflare toont fout 502 of 1033 | Container draait niet, of zit niet in het netwerk `tunnel`, of cloudflared is gestopt | Beide containers starten; netwerk van wtc-website controleren |
| Aanmelden: AADSTS90002 (tenant not found) | Verkeerde of lege AZURE\_TENANT\_ID | Tenant ID uit Entra > Overview overnemen |
| Aanmelden: AADSTS50011 (redirect URI mismatch) | Domein niet als redirect URI geregistreerd | Redirect URI toevoegen in de app-registratie (met /admin/login/callback/) |
| Aanmelden: AADSTS7000222 of invalid\_client | Client secret verlopen of verkeerd | Nieuw secret maken, AZURE\_CLIENT\_SECRET aanpassen |
| Aangemeld, maar "geen toegang" | E-mailadres staat niet in Instellingen > Toegang | Adres toevoegen (of in BOOTSTRAP\_ADMIN\_EMAILS) |
| Er komen geen mails toe | Mail.Send zonder admin consent, afzender staat niet in de ApplicationAccessPolicy, of secret verlopen | Eerst E-mails > Verstuurde mails in de admin: de foutmelding staat bij de mislukte mail. Daarna logs zoeken op "Graph"; rechten en policy nakijken |
| Betaalknop doet niets | Content-Security-Policy blokkeert de doorverwijzing naar Stripe (opgelost in de code: form-action laat checkout.stripe.com toe) | Bij aanpassingen aan de CSP checkout.stripe.com laten staan |
| Bestelling blijft op *Aan het afrekenen* na betaling | Webhook komt niet aan of wordt geweigerd | Stripe > webhook > Gebeurtenissen: 301 = slash vergeten in de URL; 400 = verkeerd whsec-geheim; 500 = fout in de site (logs). Daarna de levering opnieuw versturen |
| Webhook gaf 500 met "not a dict" | Oud probleem met stripe-bibliotheek v16 | Opgelost; de site leest nu de ruwe JSON |
| Cyql-sync faalt met depth- of complexity-fout | Een vraag is te diep (max. 5) of te duur (max. 200) | Minder klassementen tonen; in de code vragen opsplitsen. Geen cyql\_schema draaien om te zoeken |
| Cyql-sync faalt met budget-fout | Weekbudget van 5.000 op | Wachten tot maandag; niet herhaaldelijk op *Nu synchroniseren* drukken |
| Inhoudswijziging in Wagtail is na een redeploy terug weg | seed\_site of een migratie zet bepaalde inhoud terug | Gekend en nog op te lossen; noteer welke pagina of instelling het was |

### Een wijziging laten maken

Vraag de wijziging aan Claude in het project, met de afspraken uit CLAUDE.md in de repository. Elke wijziging wordt getest (`DEBUG=1 python manage.py test apps` en `makemigrations --check`) en komt als pull request; jij merget en redeployt.

## Livegang-checklist (wtc-zonnebeke.be)

Voorbereiding vanaf 1 december 2026, live op 1 januari 2027.

### Voorbereiding (december)

- [ ] Cloudflare: public hostnames voor wtc-zonnebeke.be en www.wtc-zonnebeke.be toevoegen (oude DNS-records eerst weg)
- [ ] Entra: redirect URI `https://www.wtc-zonnebeke.be/admin/login/callback/` toevoegen
- [ ] Stack: ALLOWED\_HOSTS en CSRF\_TRUSTED\_ORIGINS uitbreiden met de nieuwe domeinen
- [ ] Turnstile (als gebruikt): nieuwe hostnames toevoegen
- [ ] Mail-DNS: SPF, DKIM en DMARC nakijken en testen (bv. een mail naar een Gmail-adres, *Origineel bericht tonen*: alles PASS)
- [ ] Privacyverklaring bijwerken (Stripe, Microsoft 365, Cyql als verwerkers)
- [ ] Clubreglement goedgekeurd door het bestuur
- [ ] Lidgeld: prijsverhoging op 1 december gezet
- [ ] A4-handleiding voor bestuur en stockbeheerder
- [ ] Ledengroep: krijgt de groep een adres op het nieuwe domein, pas het dan aan onder Cyql > Instellingen > Ledengroep (de welkomstmail blijft uit; enkel een nieuwe groep heeft stap 7 van *Ledengroep* opnieuw nodig)

### Op de dag zelf

- [ ] Back-up maken (`backup_db`)
- [ ] Stack: BASE\_URL op `https://www.wtc-zonnebeke.be`, SITE\_NOINDEX op 0
- [ ] Stripe: live sleutel in STRIPE\_SECRET\_KEY
- [ ] Stripe: **nieuwe live webhook** op `https://www.wtc-zonnebeke.be/stripe/webhook/` (slash op het einde, snapshot, vier events) en het nieuwe whsec in STRIPE\_WEBHOOK\_SECRET
- [ ] Stack updaten
- [ ] Microsoft 365: MFA terug aanzetten voor het info@-account
- [ ] Oud domein wtczonnebeke.be laten doorverwijzen naar het nieuwe (Cloudflare *Redirect Rules*, 301), maar /index.php?id=900 moet op beide werken
- [ ] QR-codes op de pijltjes testen met een gsm (adres /index.php?id=900 blijft ongewijzigd)
- [ ] Echte bestelling van een klein bedrag, daarna terugbetalen in Stripe
- [ ] Formulier invullen en de melding controleren
- [ ] Aanmelden op /admin/ en in de stock-app op de gsm van de stockbeheerder
- [ ] Google Search Console: nieuw domein toevoegen en verifiëren via Cloudflare (er is nog geen sitemap; kan later)

### Na een week

- [ ] Stripe-webhook: alle leveringen 200
- [ ] Cyql-verslagen: elke nacht geslaagd, budget in orde
- [ ] Back-ups aanwezig in /data/backups en gekopieerd buiten de Pi
- [ ] DMARC van p=none naar p=quarantine als de rapporten in orde zijn
- [ ] Testsleutels van Stripe en de test-webhook verwijderen

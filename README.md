# Website WTC Zonnebeke

Openbare website van wielertoeristenclub WTC Zonnebeke vzw, met een beheeromgeving voor het bestuur.

- **Techniek:** Python 3.13, Django 5.2, Wagtail 7.4 (CMS), SQLite, Gunicorn, WhiteNoise.
- **Hosting:** één Docker-container (app + database) op een Raspberry Pi met Portainer, achter een Cloudflare Tunnel.
- **Aanmelden beheer:** Microsoft 365 (Entra ID). Rollen *Beheerder* en *Stockbeheerder* stel je in via Instellingen > Toegang.
- **Geen cookiebanner nodig:** enkel strikt noodzakelijke cookies, geen tracking, YouTube laadt pas na een klik.

## Fasering

1. Basis en inhoud: pagina's, huisstijl, sponsors, clubreglement, QR-infopagina, contactformulier, SSO, Docker. **(deze versie)**
2. Cyql: clubkalender, klassement, ledenlijst voor lidcontrole.
3. Webshop en stockbeheer met Stripe, mobiele stockomgeving (PWA).
4. Formulierenbouwer en inschrijvingen.
5. Livegang op wtc-zonnebeke.be.

## Installatie op de Raspberry Pi

### 1. Microsoft 365: app-registratie

1. Ga naar [Entra admin center](https://entra.microsoft.com) > *Applications* > *App registrations* > *New registration*.
2. Naam: `WTC Website`. Account types: *Accounts in this organizational directory only*.
3. Redirect URI: platform *Web*, adres `https://www.wtczonnebeke.be/admin/login/callback/`
   (voeg later ook `https://www.wtc-zonnebeke.be/admin/login/callback/` toe bij de overstap).
4. Noteer de **Application (client) ID**.
5. *Certificates & secrets* > *New client secret*. Kopieer de **Value** meteen; die zie je maar één keer.
6. *API permissions*:
   - Microsoft Graph > *Delegated* > `openid`, `profile`, `email`, `User.Read` (standaard al aanwezig).
   - Microsoft Graph > *Application* > `Mail.Send`, en klik op *Grant admin consent*.
7. Beperk `Mail.Send` tot de mailbox info@wtczonnebeke.be, anders mag de app vanuit elke mailbox mailen.
   In Exchange Online PowerShell:
   ```powershell
   New-ApplicationAccessPolicy -AppId <client-id> -PolicyScopeGroupId info@wtczonnebeke.be `
     -AccessRight RestrictAccess -Description "WTC Website mag enkel als info@ mailen"
   ```

### 2. Portainer: stack

1. *Stacks* > *Add stack* > *Repository*, repository `https://github.com/ThomasMidgley/WTCZonnebeke`, compose-pad `docker-compose.yml`.
2. Is de repository of het image privé, voeg dan onder *Registries* `ghcr.io` toe met je GitHub-gebruikersnaam
   en een *personal access token* met het recht `read:packages`.
3. Vul de variabelen in volgens [.env.example](.env.example). Minstens `SECRET_KEY`, `AZURE_CLIENT_ID` en `AZURE_CLIENT_SECRET`.
4. Deploy. Bij de eerste start maakt de container zelf de database en alle startinhoud aan.
5. Wil je automatisch bijwerken bij een nieuwe versie: zet in de stack *GitOps updates* of een *webhook* aan.

Alle gegevens (database, foto's, back-ups) staan in het volume `wtc-data` (`/data` in de container).
Elke nacht om 02.30 uur komt er een back-up in `/data/backups`; back-ups ouder dan 30 dagen worden opgeruimd.
Neem dat volume mee in de back-up van de Pi. (Kopie naar OneDrive volgt in een latere fase.)

### 3. Cloudflare Tunnel

De website zit in hetzelfde Docker-netwerk als je cloudflared-container (standaard `tunnel`;
een andere naam stel je in met `TUNNEL_NETWORK`). Er staat geen poort open op de Pi.

In *Cloudflare Zero Trust* > *Networks* > *Tunnels* > je bestaande tunnel > *Public hostnames*, voeg toe:

| Subdomain | Domain | Service |
| --- | --- | --- |
| `www` | `wtczonnebeke.be` | `http://wtc-website:8000` |
| (leeg) | `wtczonnebeke.be` | `http://wtc-website:8000` |

Optioneel en aangeraden: *Access* > *Applications* > *Self-hosted* voor `www.wtczonnebeke.be/admin`,
met Microsoft Entra ID als login. Dan ziet niemand buiten de club zelfs het aanmeldscherm.

### 4. Cyql

1. In het [Cyql-dashboard](https://dashboard.cyql.app) > *Settings* > *API* > *New API key*. Kopieer de sleutel meteen.
2. Zet hem in de stack als `CYQL_API_KEY` en klik *Update the stack*.
3. Elke nacht haalt de site de komende ritten en activiteiten, de klassementen en de goedgekeurde leden op,
   op het uur bij *Instellingen* > *Integraties*.
4. In het menu **Cyql**:
   - *Klassementen*: kies welke klassementen op de website komen (en in welke volgorde).
     Verborgen klassementen kosten geen API-budget.
   - *Leden*: de ledenlijst voor de lidcontrole (enkel lezen, enkel voor beheerders).
   - *Synchronisaties*: het verslag van elke sync, met het resterende weekbudget.
5. Meteen synchroniseren: *Instellingen* > *Cyql nu synchroniseren*.

Handig in de console van de container (Portainer > container > *Console*):

| Commando | Wat |
| --- | --- |
| `python manage.py cyql_sync` | Nu synchroniseren |
| `python manage.py cyql_schema` | Toont het schema van de API. **Duur**: enkel gebruiken als het weekbudget het toelaat |

Cyql rekent met een budget: 200 per vraag en 5.000 per week voor de hele club (reset maandag).
Eén sync kost ongeveer 300 (met één getoond klassement). De site vraagt daarom alles één keer per nacht op en toont bezoekers
enkel wat in de eigen database staat. Op het klassement staan standaard enkel voornaam en initiaal;
volledige namen zet je aan op de pagina Klassement.

### 5. Eerste keer aanmelden

Ga naar `https://www.wtczonnebeke.be/admin/` en meld je aan met info@wtczonnebeke.be.
Onder **Instellingen** vind je: Huisstijl, Clubgegevens, Clubreglement, Vzw-statuten, Cyql-app, Integraties, Toegang en QR-info pijltjes.
Sponsors beheer je via het menu **Sponsors**.

**Noodtoegang** als Microsoft 365 niet werkt: zet `ALLOW_PASSWORD_LOGIN=1`, open in Portainer een console in de container en voer
`python manage.py createsuperuser` uit. Zet het daarna weer op `0`.

## Ontwikkelen

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DEBUG=1
python manage.py migrate
python manage.py seed_site
python manage.py createsuperuser   # lokaal, met ALLOW_PASSWORD_LOGIN=1
python manage.py runserver
python manage.py test apps
```

Inhoud aanpassen gebeurt in de beheeromgeving, niet in de code. `seed_site` maakt enkel aan wat nog niet bestaat.

## Structuur

| Map | Inhoud |
| --- | --- |
| `config/` | Django-instellingen en URL's |
| `apps/core/` | Instellingen (huisstijl, clubgegevens, toegang, ...), sponsors, QR-pagina, e-mail via Graph, back-up |
| `apps/pages/` | Paginatypes van Wagtail (home, bestuur, evenement, contact, ...) |
| `apps/accounts/` | Aanmelden via Microsoft 365 en rollen |
| `templates/`, `static/` | HTML, CSS (geen framework) en een klein script voor de YouTube-film |
| `seed/` | Startinhoud: gecorrigeerd clubreglement, originele bijlagen, productfoto's |

# Werkafspraken voor deze repository

- Taal: alle teksten voor gebruikers, beheerders, commentaar en commitberichten in het Nederlands (Vlaams). Code-identifiers in het Engels.
- Snelheid gaat voor op stijl: geen JavaScript-frameworks, geen externe lettertypes of CDN's, geen trackers. Externe inhoud (YouTube) pas laden na een klik.
- Geen cookies behalve strikt noodzakelijke (sessie, CSRF). Geen cookiebanner toevoegen.
- Alles moet werken op een smartphone; test op 390 px breed. De stockbeheerder gebruikt enkel een Android-gsm.
- Inhoud hoort in Wagtail (pagina's, instellingen, snippets), niet hardgecodeerd in templates. Nieuwe instellingen: een `BaseGenericSetting` in `apps/core/models.py`.
- Geheimen alleen via omgevingsvariabelen (zie `.env.example`), nooit in de database of in Git.
- `/index.php?id=900` is het adres in de QR-codes op de pijltjes en mag nooit veranderen.
- Footer: "Webdesign door Post Mill (link www.postmill.be) · © WTC Zonnebeke vzw".
- `seed_site` moet idempotent blijven: enkel aanmaken wat nog niet bestaat.
- Voor elke wijziging: `DEBUG=1 python manage.py test apps` en `makemigrations --check`.
- De container draait op een Raspberry Pi (arm64): geen pakketten die niet voor arm64 bestaan.

"""Test of werk de ledengroep in Microsoft 365 bij zonder Cyql (kost geen Cyql-budget).

    python manage.py ledengroep              # controle: rechten, groep, wat er zou gebeuren (wijzigt niets)
    python manage.py ledengroep --uitvoeren  # de groep echt bijwerken met de ledenlijst die al in de database staat
"""

from django.core.management.base import BaseCommand

from apps.core.models import CyqlApp
from apps.cyql.member_group import Graph, MemberGroupError, find_group, sync_member_group, token_roles

NEEDED = ["GroupMember.Read.All", "GroupMember.ReadWrite.All", "User.Invite.All", "User.Read.All"]


class Command(BaseCommand):
    help = "Ledengroep testen of bijwerken zonder Cyql. Zonder --uitvoeren wordt niets gewijzigd."

    def add_arguments(self, parser):
        parser.add_argument("--uitvoeren", action="store_true", help="De groep echt bijwerken.")

    def handle(self, *args, **options):
        settings = CyqlApp.load()
        if not settings.member_group:
            self.stderr.write("Geen adres ingesteld bij Cyql > Instellingen > Ledengroep.")
            raise SystemExit(1)
        self.stdout.write(f"Groep: {settings.member_group}")
        if settings.member_group_test_emails:
            self.stdout.write(f"Testadressen: {', '.join(settings.member_group_test_emails)}")

        try:
            roles, tenant, app = token_roles()
        except Exception as exc:
            self.stderr.write(f"Geen token van Microsoft: {exc}")
            raise SystemExit(1)
        self.stdout.write(f"App: {app or '?'} in tenant {tenant}")
        self.stdout.write(f"Rechten in het token: {', '.join(roles) or 'geen'}")
        missing = [role for role in NEEDED if role not in roles]
        if missing:
            self.stderr.write(
                f"Ontbreekt in het token: {', '.join(missing)}. Voeg ze toe als 'Application permissions' "
                "(niet 'Delegated') en klik op 'Grant admin consent'. Daarna kan het enkele minuten duren."
            )

        graph = Graph()
        try:
            group_id = find_group(graph, settings.member_group)
            self.stdout.write(self.style.SUCCESS(f"Groep gevonden: {group_id}"))
            result = sync_member_group(graph=graph, dry_run=not options["uitvoeren"])
        except MemberGroupError as exc:
            self.stderr.write(f"Mislukt: {exc}")
            raise SystemExit(1)
        label = "Bijgewerkt" if options["uitvoeren"] else "Proef (niets gewijzigd)"
        self.stdout.write(self.style.SUCCESS(f"{label}: {result}"))

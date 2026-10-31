from django.core.management.base import BaseCommand

from apps.cyql.sync import run_sync


class Command(BaseCommand):
    help = "Synchroniseert nu met Cyql (gebeurt ook elke nacht automatisch)."

    def handle(self, *args, **options):
        run = run_sync()
        self.stdout.write(run.message)
        if run.remaining_budget is not None:
            self.stdout.write(f"Resterend weekbudget van de club: {run.remaining_budget}")
        if not run.ok:
            raise SystemExit(1)

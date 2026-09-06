from django.core.management.base import BaseCommand

from payment.tasks import purge_old_payment_payloads_task


class Command(BaseCommand):
    help = "Удаляет payload из старых событий платежей, сохраняя аудит статусов."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать количество событий без изменения базы.",
        )

    def handle(self, *args, **options):
        updated = purge_old_payment_payloads_task(dry_run=options["dry_run"])
        if options["dry_run"]:
            self.stdout.write(f"Будет очищено событий: {updated}")
        else:
            self.stdout.write(self.style.SUCCESS(f"Очищено событий: {updated}"))

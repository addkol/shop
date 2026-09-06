from django.core.management.base import BaseCommand

from shop.order_lifecycle import cancel_expired_orders


class Command(BaseCommand):
    help = "Отменяет просроченные неоплаченные заказы и возвращает товары на склад."

    def handle(self, *args, **options):
        cancelled = cancel_expired_orders()
        self.stdout.write(self.style.SUCCESS(f"Отменено просроченных заказов: {cancelled}"))

from django.db import models


class PaymentEvent(models.Model):
    order = models.ForeignKey(
        "shop.Order",
        on_delete=models.PROTECT,
        related_name="payment_events",
        null=True,
        blank=True,
        verbose_name="Заказ",
    )
    provider_event_id = models.CharField(max_length=160, unique=True, verbose_name="ID события провайдера")
    payment_id = models.CharField(max_length=128, db_index=True, verbose_name="ID платежа")
    status = models.CharField(max_length=32, verbose_name="Статус")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Сумма")
    payload = models.JSONField(default=dict, verbose_name="Данные события")
    signature_valid = models.BooleanField(default=False, verbose_name="Подпись проверена")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Обработано")
    received_at = models.DateTimeField(auto_now_add=True, verbose_name="Получено")

    class Meta:
        ordering = ("-received_at",)
        verbose_name = "Событие платежа"
        verbose_name_plural = "События платежей"

    def __str__(self):
        return f"{self.provider_event_id}: {self.status}"

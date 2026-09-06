import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("shop", "0006_order_lifecycle_reviews_and_validation")]

    operations = [
        migrations.CreateModel(
            name="PaymentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_event_id", models.CharField(max_length=160, unique=True, verbose_name="ID события провайдера")),
                ("payment_id", models.CharField(db_index=True, max_length=128, verbose_name="ID платежа")),
                ("status", models.CharField(max_length=32, verbose_name="Статус")),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Сумма")),
                ("payload", models.JSONField(default=dict, verbose_name="Данные события")),
                ("signature_valid", models.BooleanField(default=False, verbose_name="Подпись проверена")),
                ("processed_at", models.DateTimeField(blank=True, null=True, verbose_name="Обработано")),
                ("received_at", models.DateTimeField(auto_now_add=True, verbose_name="Получено")),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_events", to="shop.order", verbose_name="Заказ")),
            ],
            options={"verbose_name": "Событие платежа", "verbose_name_plural": "События платежей", "ordering": ("-received_at",)},
        ),
    ]

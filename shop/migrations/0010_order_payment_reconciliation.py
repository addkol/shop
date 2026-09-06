from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0009_production_data_integrity"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_checked_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Статус оплаты проверен"),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_reconciliation_failures",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Ошибки сверки оплаты"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                fields=["status", "payment_status", "payment_checked_at"],
                name="order_payment_check_idx",
            ),
        ),
    ]

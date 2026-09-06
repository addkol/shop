from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shop", "0006_order_lifecycle_reviews_and_validation")]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("waiting", "В ожидании"),
                    ("success", "Успешно"),
                    ("failed", "Ошибка"),
                    ("refund_required", "Требуется возврат"),
                ],
                default="waiting",
                max_length=20,
                verbose_name="Статус оплаты",
            ),
        ),
    ]

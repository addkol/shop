import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shop", "0007_order_refund_required")]

    operations = [
        migrations.AlterField(
            model_name="wholesaleprice",
            name="min_quantity",
            field=models.PositiveIntegerField(
                help_text="Например, 9 — оптовая цена начнёт действовать с 10 штук.",
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Опт применяется после количества",
            ),
        ),
    ]

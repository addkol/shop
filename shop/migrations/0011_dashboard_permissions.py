from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("shop", "0010_order_payment_reconciliation")]
    operations = [
        migrations.AlterModelOptions(
            name="product",
            options={"ordering": ("-created_at",), "verbose_name": "Товар", "verbose_name_plural": "Товары",
                     "permissions": [("adjust_stock", "Корректировать доступный остаток")]},
        ),
        migrations.AlterModelOptions(
            name="order",
            options={"ordering": ("-created_at",), "verbose_name": "Заказ", "verbose_name_plural": "Заказы",
                     "permissions": [("fulfill_order", "Отправлять и доставлять оплаченные заказы"),
                                     ("cancel_order", "Отменять ожидающие заказы")]},
        ),
    ]

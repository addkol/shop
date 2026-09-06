from django.db import migrations, models
from django.db.models import Q


def normalize_empty_payment_ids(apps, schema_editor):
    Order = apps.get_model("shop", "Order")
    Order.objects.filter(payment_id="").update(payment_id=None)


def restore_empty_payment_ids(apps, schema_editor):
    Order = apps.get_model("shop", "Order")
    Order.objects.filter(payment_id__isnull=True).update(payment_id="")


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0008_wholesale_threshold_semantics"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="payment_id",
            field=models.CharField(blank=True, max_length=128, null=True, verbose_name="ID платежа"),
        ),
        migrations.RunPython(normalize_empty_payment_ids, restore_empty_payment_ids),
        migrations.AlterField(
            model_name="order",
            name="payment_id",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name="ID платежа"),
        ),
        migrations.AddConstraint(
            model_name="address",
            constraint=models.UniqueConstraint(
                condition=Q(is_default=True),
                fields=("user",),
                name="unique_default_address_user",
            ),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                fields=["status", "payment_status", "payment_expires_at"],
                name="order_payment_expiry_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=Q(total_price__gte=0),
                name="nonnegative_order_total",
            ),
        ),
    ]

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import shop.validators
from django.conf import settings
from django.db import migrations, models


def preserve_existing_wholesale_behavior(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    WholesalePrice = apps.get_model("shop", "WholesalePrice")
    for product in Product.objects.all().iterator():
        if not WholesalePrice.objects.filter(product_id=product.pk).exists():
            WholesalePrice.objects.create(
                product_id=product.pk,
                min_quantity=5,
                price=(product.price * Decimal("0.80")).quantize(Decimal("0.01")),
            )


def normalize_main_images(apps, schema_editor):
    ProductImage = apps.get_model("shop", "ProductImage")
    product_ids = (
        ProductImage.objects.filter(is_main=True)
        .values_list("product_id", flat=True)
        .distinct()
    )
    for product_id in product_ids:
        main_ids = list(
            ProductImage.objects.filter(product_id=product_id, is_main=True)
            .order_by("ordering", "id")
            .values_list("id", flat=True)
        )
        ProductImage.objects.filter(id__in=main_ids[1:]).update(is_main=False)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("shop", "0005_product_brand_and_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="is_saved",
            field=models.BooleanField(default=True, verbose_name="Сохранён в профиле"),
        ),
        migrations.AddField(
            model_name="order",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Оплачено"),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_attempts",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Попытки оплаты"),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_expires_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Оплатить до"),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_last_error",
            field=models.TextField(blank=True, verbose_name="Последняя ошибка оплаты"),
        ),
        migrations.AddField(
            model_name="order",
            name="stock_released",
            field=models.BooleanField(default=False, verbose_name="Резерв возвращён"),
        ),
        migrations.AlterField(
            model_name="product",
            name="image",
            field=models.ImageField(blank=True, upload_to="products/", validators=[shop.validators.validate_product_image], verbose_name="Изображение"),
        ),
        migrations.AlterField(
            model_name="product",
            name="video",
            field=models.FileField(blank=True, upload_to="products/videos/", validators=[shop.validators.validate_product_video], verbose_name="Видео"),
        ),
        migrations.AlterField(
            model_name="productimage",
            name="image",
            field=models.ImageField(upload_to="products/gallery/", validators=[shop.validators.validate_product_image], verbose_name="Изображение"),
        ),
        migrations.AlterField(
            model_name="wholesaleprice",
            name="min_quantity",
            field=models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(2)], verbose_name="Минимальное количество"),
        ),
        migrations.AlterField(
            model_name="wholesaleprice",
            name="price",
            field=models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))], verbose_name="Цена для опта"),
        ),
        migrations.CreateModel(
            name="Review",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name="Оценка")),
                ("text", models.TextField(max_length=2000, verbose_name="Отзыв")),
                ("is_approved", models.BooleanField(db_index=True, default=False, verbose_name="Опубликован")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создан")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлён")),
                ("order_item", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="review", to="shop.orderitem", verbose_name="Позиция заказа")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="shop.product", verbose_name="Товар")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reviews", to=settings.AUTH_USER_MODEL, verbose_name="Покупатель")),
            ],
            options={"verbose_name": "Отзыв", "verbose_name_plural": "Отзывы", "ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="review",
            constraint=models.UniqueConstraint(fields=("user", "product"), name="unique_user_product_review"),
        ),
        migrations.RunPython(preserve_existing_wholesale_behavior, migrations.RunPython.noop),
        migrations.RunPython(normalize_main_images, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="productimage",
            constraint=models.UniqueConstraint(condition=models.Q(("is_main", True)), fields=("product",), name="unique_main_image_per_product"),
        ),
    ]

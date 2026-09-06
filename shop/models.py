import secrets
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .validators import validate_product_image, validate_product_video


class Category(models.Model):
    name = models.CharField(max_length=150, verbose_name="Название")
    slug = models.SlugField(max_length=160, unique=True, verbose_name="Слаг")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
        verbose_name="Родительская категория",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        ordering = ("name",)
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:category", kwargs={"slug": self.slug})

    @property
    def icon_name(self):
        icon_map = {
            "mobile-accessories": "phone",
            "phone-accessories": "phone",
            "home-appliances": "home",
            "cosmetics": "beauty",
            "clothing": "clothes",
            "shoes": "shoes",
            "sport": "sport",
            "computers": "laptop",
            "phones": "phone",
            "tablets": "tablet",
            "beauty-care": "beauty",
            "bags": "bag",
            "cookware": "cookware",
            "household": "home",
            "toys": "toy",
            "stationery": "stationery",
            "lighting": "light",
            "decor": "decor",
            "home-textile": "textile",
            "bathroom": "bath",
            "home-accessories": "decor",
            "furniture": "furniture",
        }
        return icon_map.get(self.slug, "bag")


class Product(models.Model):
    name = models.CharField(max_length=200, verbose_name="Название")
    slug = models.SlugField(max_length=220, unique=True, verbose_name="Слаг")
    description = models.TextField(verbose_name="Описание")
    additional_description = models.TextField(blank=True, verbose_name="Дополнительное описание")
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Цена")
    stock = models.PositiveIntegerField(default=0, verbose_name="Количество на складе")
    image = models.ImageField(
        upload_to="products/",
        blank=True,
        validators=[validate_product_image],
        verbose_name="Изображение",
    )
    video = models.FileField(
        upload_to="products/videos/",
        blank=True,
        validators=[validate_product_video],
        verbose_name="Видео",
    )
    brand = models.CharField(max_length=100, blank=True, db_index=True, verbose_name="Бренд")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="Категория")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        permissions = [("adjust_stock", "Корректировать доступный остаток")]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:product-detail", kwargs={"slug": self.slug})

    def _prefetched_wholesale_prices(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        rules = prefetched.get("wholesale_prices")
        if rules is None:
            rules = self.wholesale_prices.all()
        return list(rules)

    def get_price_for_quantity(self, quantity):
        quantity = max(1, int(quantity))
        active_prices = [
            tier["price"]
            for tier in self.get_pricing_tiers()
            if quantity >= tier["min_quantity"]
        ]
        return min(active_prices, default=self.price)

    def get_pricing_tiers(self):
        rules = sorted(self._prefetched_wholesale_prices(), key=lambda rule: rule.min_quantity)
        tiers = [
            {"min_quantity": rule.min_quantity + 1, "price": min(rule.price, self.price)}
            for rule in rules
        ]

        tiers.sort(key=lambda tier: tier["min_quantity"])
        best_price = self.price
        for tier in tiers:
            best_price = min(best_price, tier["price"])
            tier["price"] = best_price
        return tiers

    @property
    def wholesale_price(self):
        tiers = self.get_pricing_tiers()
        return min([self.price, *[tier["price"] for tier in tiers]])

    @property
    def wholesale_min_quantity(self):
        tiers = self.get_pricing_tiers()
        return tiers[0]["min_quantity"] if tiers else None

    @property
    def sku(self):
        return f"EM-{self.pk:05d}"

    @staticmethod
    def _file_exists(file_field):
        if not file_field:
            return False
        if not isinstance(file_field.storage, FileSystemStorage):
            return bool(file_field.name)
        try:
            return bool(file_field.name and file_field.storage.exists(file_field.name))
        except (OSError, ValueError):
            return False

    def _prefetched_gallery_images(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        images = prefetched.get("images")
        if images is None:
            images = self.images.all()
        return [image for image in images if self._file_exists(image.image)]

    @property
    def gallery_images(self):
        images = self._prefetched_gallery_images()
        main_images = [image for image in images if image.is_main]
        secondary_images = [image for image in images if not image.is_main]
        return main_images + secondary_images

    @property
    def main_image_url(self):
        gallery_images = self.gallery_images
        if gallery_images:
            return gallery_images[0].image.url
        if self._file_exists(self.image):
            return self.image.url
        return ""

    @property
    def has_video(self):
        return self._file_exists(self.video)

    @property
    def media_items(self):
        items = []
        used_names = set()
        for image in self.gallery_images:
            used_names.add(image.image.name)
            items.append(
                {
                    "type": "image",
                    "url": image.image.url,
                    "alt": image.alt_text or self.name,
                    "label": image.alt_text or "Фото товара",
                }
            )

        if self._file_exists(self.image) and self.image.name not in used_names:
            items.append({"type": "image", "url": self.image.url, "alt": self.name, "label": "Основное фото"})

        if self.has_video:
            items.append({"type": "video", "url": self.video.url, "alt": self.name, "label": "Видео"})
        return items

    @property
    def available(self):
        return self.is_active and self.stock > 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images", verbose_name="Товар")
    image = models.ImageField(
        upload_to="products/gallery/",
        validators=[validate_product_image],
        verbose_name="Изображение",
    )
    alt_text = models.CharField(max_length=200, blank=True, verbose_name="Подпись")
    is_main = models.BooleanField(default=False, verbose_name="Основное")
    ordering = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ("ordering", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_main=True),
                name="unique_main_image_per_product",
            ),
        ]
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товара"

    def __str__(self):
        return f"{self.product.name}: изображение"


class WholesalePrice(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wholesale_prices", verbose_name="Товар")
    min_quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Опт применяется после количества",
        help_text="Например, 9 — оптовая цена начнёт действовать с 10 штук.",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Цена для опта",
    )

    class Meta:
        ordering = ("min_quantity",)
        verbose_name = "Оптовая цена"
        verbose_name_plural = "Оптовые цены"
        constraints = [models.UniqueConstraint(fields=["product", "min_quantity"], name="unique_product_min_quantity")]

    def __str__(self):
        return f"{self.product.name}: от {self.min_quantity + 1} шт. = {self.price}"


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart", verbose_name="Пользователь")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"

    def __str__(self):
        return f"Корзина для {self.user}"

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.select_related("product"))

    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items", verbose_name="Корзина")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Товар")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")

    class Meta:
        verbose_name = "Товар в корзине"
        verbose_name_plural = "Товары в корзине"
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="unique_cart_product"),
        ]

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def subtotal(self):
        return self.product.get_price_for_quantity(self.quantity) * self.quantity


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses", verbose_name="Пользователь")
    country = models.CharField(max_length=100, default="Киргизия", verbose_name="Страна")
    city = models.CharField(max_length=100, verbose_name="Город")
    street = models.CharField(max_length=150, verbose_name="Улица")
    building = models.CharField(max_length=50, verbose_name="Дом")
    apartment = models.CharField(max_length=50, blank=True, verbose_name="Квартира")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="Почтовый код")
    is_default = models.BooleanField(default=False, verbose_name=" По умолчанию")
    is_saved = models.BooleanField(default=True, verbose_name="Сохранён в профиле")

    class Meta:
        ordering = ("-is_default", "city", "street")
        verbose_name = "Адрес"
        verbose_name_plural = "Адреса"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_default=True),
                name="unique_default_address_user",
            ),
        ]

    def __str__(self):
        apartment = f", кв. {self.apartment}" if self.apartment else ""
        return f"{self.country}, {self.city}, {self.street} {self.building}{apartment}"

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "В ожидании"
        PAID = "paid", "Оплачено"
        SHIPPED = "shipped", "Отправлено"
        DELIVERED = "delivered", "Доставлено"
        CANCELLED = "cancelled", "Отменено"

    class PaymentMethod(models.TextChoices):
        QR = "qr", "QR код"
        CARD = "card", "Карта"
        LINK = "link", "Ссылка на оплату"

    class PaymentStatus(models.TextChoices):
        WAITING = "waiting", "В ожидании"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"
        REFUND_REQUIRED = "refund_required", "Требуется возврат"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name="Пользователь")
    shipping_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Адрес доставки")
    order_number = models.CharField(max_length=32, unique=True, blank=True, verbose_name="Номер заказа")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="Статус")
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.QR,
        verbose_name="Способ оплаты",
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.WAITING,
        verbose_name="Статус оплаты",
    )
    payment_id = models.CharField(max_length=128, blank=True, null=True, unique=True, verbose_name="ID платежа")
    payment_link = models.URLField(blank=True, verbose_name="Ссылка на оплату")
    qr_code = models.TextField(blank=True, verbose_name="QR код")
    cancellation_reason = models.TextField(blank=True, verbose_name="Причина отмены")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Отменено")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Оплачено")
    payment_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Оплатить до")
    payment_attempts = models.PositiveSmallIntegerField(default=0, verbose_name="Попытки оплаты")
    payment_last_error = models.TextField(blank=True, verbose_name="Последняя ошибка оплаты")
    payment_checked_at = models.DateTimeField(null=True, blank=True, verbose_name="Статус оплаты проверен")
    payment_reconciliation_failures = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Ошибки сверки оплаты",
    )
    stock_released = models.BooleanField(default=False, verbose_name="Резерв возвращён")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        permissions = [
            ("fulfill_order", "Отправлять и доставлять оплаченные заказы"),
            ("cancel_order", "Отменять ожидающие заказы"),
        ]
        indexes = [
            models.Index(
                fields=["status", "payment_status", "payment_expires_at"],
                name="order_payment_expiry_idx",
            ),
            models.Index(
                fields=["status", "payment_status", "payment_checked_at"],
                name="order_payment_check_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_price__gte=Decimal("0.00")),
                name="nonnegative_order_total",
            ),
        ]

    def __str__(self):
        return self.order_number or f"Заказ №{self.pk}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_order_number():
        return f"KG{timezone.now():%Y%m%d}{secrets.token_hex(4).upper()}"

    def get_absolute_url(self):
        return reverse("shop:order-success", kwargs={"order_number": self.order_number})

    @property
    def can_be_paid(self):
        if self.status != self.Status.PENDING or self.payment_status != self.PaymentStatus.WAITING:
            return False
        if self.stock_released:
            return False
        return not self.payment_expires_at or self.payment_expires_at > timezone.now()

    @property
    def can_be_cancelled(self):
        return (
            self.status == self.Status.PENDING
            and self.payment_status == self.PaymentStatus.WAITING
            and not self.stock_released
        )


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name="Заказ")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Товар")
    product_name = models.CharField(max_length=200, verbose_name="Название товара")
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Цена")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")

    class Meta:
        verbose_name = "Товар в заказе"
        verbose_name_plural = "Товары в заказе"

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews", verbose_name="Товар")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name="Покупатель",
    )
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="review",
        verbose_name="Позиция заказа",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Оценка",
    )
    text = models.TextField(max_length=2000, verbose_name="Отзыв")
    is_approved = models.BooleanField(default=False, db_index=True, verbose_name="Опубликован")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_user_product_review"),
        ]
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"

    def __str__(self):
        return f"{self.product}: {self.rating}/5"

import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


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


class Product(models.Model):
    name = models.CharField(max_length=200, verbose_name="Название")
    slug = models.SlugField(max_length=220, unique=True, verbose_name="Слаг")
    description = models.TextField(verbose_name="Описание")
    additional_description = models.TextField(blank=True, verbose_name="Дополнительное описание")
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Цена")
    stock = models.PositiveIntegerField(default=0, verbose_name="Количество на складе")
    image = models.ImageField(upload_to="products/", blank=True, verbose_name="Изображение")
    video = models.FileField(upload_to="products/videos/", blank=True, verbose_name="Видео")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="Категория")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

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
        rules = sorted(self._prefetched_wholesale_prices(), key=lambda rule: rule.min_quantity, reverse=True)
        for rule in rules:
            if quantity >= rule.min_quantity:
                return rule.price
        return self.price

    @staticmethod
    def _file_exists(file_field):
        if not file_field:
            return False
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
        for image in self.gallery_images:
            items.append(
                {
                    "type": "image",
                    "url": image.image.url,
                    "alt": image.alt_text or self.name,
                    "label": image.alt_text or "Фото товара",
                }
            )

        if self._file_exists(self.image):
            items.append({"type": "image", "url": self.image.url, "alt": self.name, "label": "Основное фото"})

        if self.has_video:
            items.append({"type": "video", "url": self.video.url, "alt": self.name, "label": "Видео"})
        return items

    @property
    def available(self):
        return self.is_active and self.stock > 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images", verbose_name="Товар")
    image = models.ImageField(upload_to="products/gallery/", verbose_name="Изображение")
    alt_text = models.CharField(max_length=200, blank=True, verbose_name="Подпись")
    is_main = models.BooleanField(default=False, verbose_name="Основное")
    ordering = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ("ordering", "id")
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товара"

    def __str__(self):
        return f"{self.product.name} image"


class WholesalePrice(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wholesale_prices", verbose_name="Товар")
    min_quantity = models.PositiveIntegerField(verbose_name="Минимальное количество")
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Цена для опта")

    class Meta:
        ordering = ("min_quantity",)
        verbose_name = "Оптовая цена"
        verbose_name_plural = "Оптовые цены"
        constraints = [models.UniqueConstraint(fields=["product", "min_quantity"], name="unique_product_min_quantity")]

    def __str__(self):
        return f"{self.product.name}: {self.min_quantity}+ = {self.price}"


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

    class Meta:
        ordering = ("-is_default", "city", "street")
        verbose_name = "Адрес"
        verbose_name_plural = "Адреса"

    def __str__(self):
        apartment = f", apt. {self.apartment}" if self.apartment else ""
        return f"{self.country}, {self.city}, {self.street} {self.building}{apartment}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)


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
    payment_id = models.CharField(max_length=128, blank=True, verbose_name="ID платежа")
    payment_link = models.URLField(blank=True, verbose_name="Ссылка на оплату")
    qr_code = models.TextField(blank=True, verbose_name="QR код")
    cancellation_reason = models.TextField(blank=True, verbose_name="Причина отмены")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Отменено")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

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
        return self.status == self.Status.PENDING and self.payment_status == self.PaymentStatus.WAITING

    @property
    def can_be_cancelled(self):
        return self.can_be_paid


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

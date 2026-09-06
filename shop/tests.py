from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from payment.models import PaymentEvent

from .models import Address, Cart, CartItem, Category, Order, OrderItem, Product, WholesalePrice
from .order_lifecycle import cancel_expired_orders
from .validators import validate_product_image, validate_product_video


class ProductPricingTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Test", slug="test")
        self.product = Product.objects.create(
            name="Test product",
            slug="test-product",
            description="Test description",
            price=Decimal("100.00"),
            stock=10,
            category=self.category,
        )

    def test_returns_base_price_when_no_wholesale_rules_exist(self):
        self.assertEqual(self.product.get_price_for_quantity(1), Decimal("100.00"))
        self.assertEqual(self.product.get_price_for_quantity(3), Decimal("100.00"))

    def test_does_not_invent_wholesale_price_without_rule(self):
        self.assertEqual(self.product.get_price_for_quantity(5), Decimal("100.00"))
        self.assertEqual(self.product.get_price_for_quantity(10), Decimal("100.00"))

    def test_returns_wholesale_price_for_large_quantity(self):
        WholesalePrice.objects.create(product=self.product, min_quantity=5, price=Decimal("90.00"))

        self.assertEqual(self.product.get_price_for_quantity(4), Decimal("100.00"))
        self.assertEqual(self.product.get_price_for_quantity(5), Decimal("100.00"))
        self.assertEqual(self.product.get_price_for_quantity(6), Decimal("90.00"))
        self.assertEqual(self.product.get_price_for_quantity(10), Decimal("90.00"))


class OrderCancellationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_client(phone_number="+996700000000")
        self.category = Category.objects.create(name="Test", slug="test-cancel")
        self.product = Product.objects.create(
            name="Cancelable product",
            slug="cancelable-product",
            description="Test description",
            price=Decimal("100.00"),
            stock=3,
            category=self.category,
        )
        self.address = Address.objects.create(
            user=self.user,
            country="Кыргызстан",
            city="Бишкек",
            street="Тестовая",
            building="1",
        )
        self.order = Order.objects.create(
            user=self.user,
            shipping_address=self.address,
            total_price=Decimal("200.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            price=Decimal("100.00"),
            quantity=2,
        )
        self.product.stock = 1
        self.product.save(update_fields=["stock", "updated_at"])

    def test_cancel_unpaid_order_saves_reason_and_restores_stock(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("shop:cancel-order", kwargs={"order_number": self.order.order_number}),
            {"reason": "Передумал покупать этот товар"},
        )

        self.assertRedirects(response, reverse("accounts:profile"), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        self.assertEqual(self.order.cancellation_reason, "Передумал покупать этот товар")
        self.assertIsNotNone(self.order.cancelled_at)
        self.assertEqual(self.product.stock, 3)

        self.client.post(
            reverse("shop:cancel-order", kwargs={"order_number": self.order.order_number}),
            {"reason": "Повторная отмена не должна вернуть остаток ещё раз"},
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CheckoutPageTests(TestCase):
    def test_checkout_page_uses_secure_russian_interface(self):
        user = get_user_model().objects.create_client(phone_number="+996700000001")
        category = Category.objects.create(name="Электроника", slug="checkout-electronics")
        product = Product.objects.create(
            name="Тестовый товар",
            slug="checkout-product",
            description="Описание",
            price=Decimal("500.00"),
            stock=10,
            category=category,
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=5)
        WholesalePrice.objects.create(product=product, min_quantity=4, price=Decimal("400.00"))
        self.client.force_login(user)

        response = self.client.get(reverse("shop:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Безопасная оплата")
        self.assertContains(response, "Оптовая цена")
        self.assertContains(response, "2000,00 сом")


class ProductDetailTests(TestCase):
    def test_product_detail_uses_real_review_count_and_dynamic_tier(self):
        category = Category.objects.create(name="Электроника", slug="detail-electronics")
        product = Product.objects.create(
            name="Маршрутизатор",
            slug="detail-router",
            description="Описание",
            price=Decimal("1000.00"),
            stock=20,
            category=category,
        )
        WholesalePrice.objects.create(product=product, min_quantity=7, price=Decimal("850.00"))

        response = self.client.get(product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Оптовая цена от 8 шт.")
        self.assertContains(response, "Отзывы <span>0</span>", html=True)
        self.assertNotContains(response, "Отзывы <span>12</span>", html=True)


class SessionCartSafetyTests(TestCase):
    def test_invalid_legacy_session_values_do_not_break_cart(self):
        session = self.client.session
        session["cart"] = {"not-a-product": "wrong", "-1": None}
        session.save()

        response = self.client.get(reverse("shop:cart"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Корзина пока пуста")


class CartRedirectSafetyTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Redirect", slug="redirect")
        self.product = Product.objects.create(
            name="Redirect product",
            slug="redirect-product",
            description="Description",
            price=Decimal("100.00"),
            stock=5,
            category=category,
        )

    def test_add_to_cart_rejects_external_next_url(self):
        response = self.client.post(
            reverse("shop:add-to-cart", kwargs={"product_id": self.product.pk}),
            {"quantity": 1, "next": "https://attacker.example/phishing"},
        )

        self.assertRedirects(response, reverse("shop:cart"), fetch_redirect_response=False)

    def test_add_to_cart_accepts_local_next_url(self):
        response = self.client.post(
            reverse("shop:add-to-cart", kwargs={"product_id": self.product.pk}),
            {"quantity": 1, "next": self.product.get_absolute_url()},
        )

        self.assertRedirects(response, self.product.get_absolute_url(), fetch_redirect_response=False)


class UploadValidationTests(TestCase):
    def test_image_validator_accepts_png_signature(self):
        upload = SimpleUploadedFile(
            "product.png",
            b"\x89PNG\r\n\x1a\n" + b"safe-image-data",
            content_type="image/png",
        )

        validate_product_image(upload)

    def test_image_validator_rejects_fake_extension(self):
        upload = SimpleUploadedFile("product.jpg", b"not-an-image", content_type="image/jpeg")

        with self.assertRaises(ValidationError):
            validate_product_image(upload)

    def test_video_validator_accepts_mp4_signature(self):
        upload = SimpleUploadedFile(
            "product.mp4",
            b"\x00\x00\x00\x18ftypmp42" + b"safe-video-data",
            content_type="video/mp4",
        )

        validate_product_video(upload)


class DataIntegrityTests(TestCase):
    def test_payment_id_must_be_unique_when_present(self):
        user = get_user_model().objects.create_client(phone_number="+996700000060")
        Order.objects.create(user=user, total_price=Decimal("100.00"), payment_id="payment-unique")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(user=user, total_price=Decimal("200.00"), payment_id="payment-unique")

    def test_saving_default_address_unsets_previous_default(self):
        user = get_user_model().objects.create_client(phone_number="+996700000061")
        first = Address.objects.create(
            user=user,
            city="Бишкек",
            street="Первая",
            building="1",
            is_default=True,
        )
        second = Address.objects.create(
            user=user,
            city="Бишкек",
            street="Вторая",
            building="2",
            is_default=True,
        )

        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)


class ProductionIntegrityMigrationTests(TransactionTestCase):
    migrate_from = [("shop", "0008_wholesale_threshold_semantics")]
    migrate_to = [("shop", "0009_production_data_integrity")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        user_model = old_apps.get_model("accounts", "User")
        order_model = old_apps.get_model("shop", "Order")
        user = user_model.objects.create(
            phone_number="+996700000062",
            password="!",
            is_client=True,
            is_active=True,
        )
        order_model.objects.create(
            user_id=user.pk,
            total_price=Decimal("100.00"),
            payment_id="",
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_empty_payment_id_is_normalized(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        order_model = new_apps.get_model("shop", "Order")

        self.assertIsNone(order_model.objects.get().payment_id)


class CartAjaxPricingTests(TestCase):
    def test_quantity_change_returns_recalculated_wholesale_price(self):
        user = get_user_model().objects.create_client(phone_number="+996700000050")
        category = Category.objects.create(name="Корзина", slug="ajax-cart")
        product = Product.objects.create(
            name="Товар AJAX",
            slug="ajax-cart-product",
            description="Описание",
            price=Decimal("100.00"),
            stock=20,
            category=category,
        )
        WholesalePrice.objects.create(product=product, min_quantity=9, price=Decimal("80.00"))
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=8)
        self.client.force_login(user)

        retail_response = self.client.post(
            reverse("shop:update-cart", kwargs={"product_id": product.pk}),
            {"quantity": 9},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        wholesale_response = self.client.post(
            reverse("shop:update-cart", kwargs={"product_id": product.pk}),
            {"quantity": 10},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(retail_response.status_code, 200)
        self.assertEqual(retail_response.json()["item"]["unit_price"], "100.00")
        self.assertFalse(retail_response.json()["item"]["is_wholesale"])
        self.assertEqual(retail_response.json()["item"]["items_until_wholesale"], 1)
        self.assertEqual(wholesale_response.status_code, 200)
        payload = wholesale_response.json()
        self.assertEqual(payload["item"]["unit_price"], "80.00")
        self.assertEqual(payload["item"]["subtotal"], "800.00")
        self.assertTrue(payload["item"]["is_wholesale"])
        self.assertEqual(payload["cart_total"], "800.00")


@override_settings(
    FINIK_USE_STUB=True,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class CheckoutFlowTests(TestCase):
    def test_checkout_reserves_stock_applies_tier_and_completes_stub_payment(self):
        user = get_user_model().objects.create_client(phone_number="+996700000030")
        category = Category.objects.create(name="Полный заказ", slug="full-checkout")
        product = Product.objects.create(
            name="Товар полного заказа",
            slug="full-checkout-product",
            description="Описание",
            price=Decimal("500.00"),
            stock=10,
            category=category,
        )
        WholesalePrice.objects.create(product=product, min_quantity=4, price=Decimal("400.00"))
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=5)
        self.client.force_login(user)

        response = self.client.post(
            reverse("shop:checkout"),
            {
                "country": "Кыргызстан",
                "city": "Бишкек",
                "street": "Тестовая",
                "building": "10",
                "apartment": "2",
                "postal_code": "720000",
                "save_address": "on",
                "payment_method": Order.PaymentMethod.QR,
            },
        )

        order = Order.objects.get(user=user)
        product.refresh_from_db()
        self.assertRedirects(response, order.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(order.total_price, Decimal("2000.00"))
        self.assertEqual(product.stock, 5)
        self.assertIsNotNone(order.payment_expires_at)
        self.assertTrue(order.payment_link.endswith(f"/pay/test/{order.payment_id}/"))
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

        payment_response = self.client.post(
            reverse("payment:stub-payment", kwargs={"payment_id": order.payment_id})
        )

        order.refresh_from_db()
        self.assertRedirects(
            payment_response,
            order.get_absolute_url(),
            fetch_redirect_response=False,
        )
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.SUCCESS)
        self.assertTrue(PaymentEvent.objects.filter(order=order, status="success").exists())


class OrderExpiryTests(TestCase):
    def test_expired_order_is_cancelled_and_stock_is_returned_once(self):
        user = get_user_model().objects.create_client(phone_number="+996700000040")
        category = Category.objects.create(name="Резерв", slug="expiry-category")
        product = Product.objects.create(
            name="Зарезервированный товар",
            slug="expiry-product",
            description="Описание",
            price=Decimal("100.00"),
            stock=3,
            category=category,
        )
        order = Order.objects.create(
            user=user,
            total_price=Decimal("200.00"),
            payment_expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            price=product.price,
            quantity=2,
        )

        self.assertEqual(cancel_expired_orders(), 1)
        self.assertEqual(cancel_expired_orders(), 0)

        order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertTrue(order.stock_released)
        self.assertEqual(product.stock, 5)

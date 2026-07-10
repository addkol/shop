from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Address, Category, Order, OrderItem, Product, WholesalePrice


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

    def test_returns_wholesale_price_for_large_quantity(self):
        WholesalePrice.objects.create(product=self.product, min_quantity=5, price=Decimal("90.00"))

        self.assertEqual(self.product.get_price_for_quantity(4), Decimal("100.00"))
        self.assertEqual(self.product.get_price_for_quantity(5), Decimal("90.00"))
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

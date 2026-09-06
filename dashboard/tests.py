from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from accounts.models import User
from payment.services import PaymentGatewayError
from shop.models import Category, Order, OrderItem, Product, Review


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_dashboard_roles", verbosity=0)
        cls.category = Category.objects.create(name="Каталог", slug="dashboard-category")
        cls.product = Product.objects.create(name="Роутер", slug="dashboard-router", description="Описание",
                                              category=cls.category, price=1200, stock=9)
        cls.customer = User.objects.create_client(phone_number="+996700887001")
        cls.order = Order.objects.create(user=cls.customer, total_price=1200)
        cls.item = OrderItem.objects.create(order=cls.order, product=cls.product, product_name=cls.product.name,
                                            price=1200, quantity=1)
        cls.review = Review.objects.create(user=cls.customer, product=cls.product, order_item=cls.item, rating=5, text="Хороший товар")
        cls.staff = {}
        for name in ["Owner", "Administrator", "Manager", "Warehouse", "Support"]:
            user = User.objects.create_user(email=name.lower() + "@example.test", password="SecurePassword456!", is_staff=True)
            user.groups.add(Group.objects.get(name=name))
            cls.staff[name] = user

    def setUp(self):
        cache.clear()

    def use_role(self, name):
        self.client.force_login(self.staff[name])

    def test_anonymous_redirect_and_customer_forbidden(self):
        self.assertRedirects(self.client.get("/dashboard/"), "/admin/login/?next=/dashboard/", fetch_redirect_response=False)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get("/dashboard/").status_code, 403)

    def test_staff_without_permissions_sees_no_business_data(self):
        user = User.objects.create_user(email="empty@example.test", is_staff=True)
        self.client.force_login(user)
        self.assertNotContains(self.client.get("/dashboard/"), self.order.order_number)
        self.assertEqual(self.client.get("/dashboard/orders/").status_code, 403)

    def test_all_pages_render_for_owner(self):
        self.use_role("Owner")
        paths = ["/dashboard/", "/dashboard/orders/", f"/dashboard/orders/{self.order.pk}/",
                 "/dashboard/products/", "/dashboard/products/new/", f"/dashboard/products/{self.product.pk}/edit/",
                 "/dashboard/categories/", "/dashboard/categories/new/", f"/dashboard/categories/{self.category.pk}/edit/",
                 "/dashboard/customers/", f"/dashboard/customers/{self.customer.pk}/",
                 "/dashboard/payments/", "/dashboard/stock/", f"/dashboard/stock/{self.product.pk}/",
                 "/dashboard/reviews/", f"/dashboard/reviews/{self.review.pk}/"]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_warehouse_permissions(self):
        self.use_role("Warehouse")
        self.assertEqual(self.client.get("/dashboard/stock/").status_code, 200)
        self.assertEqual(self.client.get("/dashboard/payments/").status_code, 403)
        self.assertEqual(self.client.get("/dashboard/customers/").status_code, 403)
        self.assertEqual(self.client.get(f"/dashboard/products/{self.product.pk}/edit/").status_code, 403)
        self.assertEqual(self.client.post(f"/dashboard/orders/{self.order.pk}/action/", {"action": "cancel", "reason": "Отмена"}).status_code, 403)

    def test_support_cannot_change_catalog_or_stock(self):
        self.use_role("Support")
        self.assertEqual(self.client.get("/dashboard/products/new/").status_code, 403)
        self.assertEqual(self.client.post(f"/dashboard/stock/{self.product.pk}/", {"quantity": 99, "expected_stock": 9, "reason": "test"}).status_code, 403)

    def test_no_manual_payment_action(self):
        self.use_role("Owner")
        response = self.client.post(f"/dashboard/orders/{self.order.pk}/action/", {"action": "paid", "payment_status": "success"})
        self.assertEqual(response.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "waiting")

    def test_cancellation_returns_stock_once(self):
        self.use_role("Manager")
        url = f"/dashboard/orders/{self.order.pk}/action/"
        self.assertEqual(self.client.post(url, {"action": "cancel", "reason": "По просьбе клиента"}).status_code, 302)
        self.client.post(url, {"action": "cancel", "reason": "Повтор"})
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertTrue(self.order.stock_released)

    def test_ship_requires_paid_and_deliver_requires_shipped(self):
        self.use_role("Warehouse")
        url = f"/dashboard/orders/{self.order.pk}/action/"
        self.client.post(url, {"action": "ship"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
        Order.objects.filter(pk=self.order.pk).update(status="paid", payment_status="success")
        self.assertEqual(self.client.post(url, {"action": "ship"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"action": "deliver"}).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "delivered")

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff["Owner"])
        self.assertEqual(client.post(f"/dashboard/orders/{self.order.pk}/action/", {"action": "cancel", "reason": "Отмена"}).status_code, 403)

    def test_stock_conflict_and_negative_rejected(self):
        self.use_role("Warehouse")
        url = f"/dashboard/stock/{self.product.pk}/"
        for quantity, expected in [(-1, 9), (20, 7)]:
            self.client.post(url, {"quantity": quantity, "expected_stock": expected, "reason": "Инвентаризация"})
            self.product.refresh_from_db()
            self.assertEqual(self.product.stock, 9)
        self.assertEqual(self.client.post(url, {"quantity": 20, "expected_stock": 9, "reason": "Поставка"}).status_code, 302)

    def test_customer_page_has_no_hashes(self):
        self.use_role("Support")
        self.customer.client_profile.set_new_code()
        self.customer.client_profile.refresh_from_db()
        response = self.client.get(f"/dashboard/customers/{self.customer.pk}/")
        self.assertNotContains(response, self.customer.client_profile.verification_code_hash)
        self.assertNotContains(response, "verification_code_hash")
        self.assertNotContains(response, "password")

    def test_filter_invalid_dates_and_search(self):
        self.use_role("Manager")
        self.assertContains(self.client.get("/dashboard/orders/", {"q": self.order.order_number}), self.order.order_number)
        self.assertNotContains(self.client.get("/dashboard/orders/", {"status": "paid"}), self.order.order_number)
        self.assertContains(self.client.get("/dashboard/orders/", {"date_from": "wrong"}), "Введите правильную дату")

    def test_category_cycle_rejected(self):
        self.use_role("Manager")
        response = self.client.post(f"/dashboard/categories/{self.category.pk}/edit/",
                                    {"name": "Каталог", "slug": self.category.slug, "parent": self.category.pk})
        self.assertContains(response, "цикл")

    def test_review_moderation(self):
        self.use_role("Support")
        self.assertEqual(self.client.post(f"/dashboard/reviews/{self.review.pk}/", {"action": "approve"}).status_code, 302)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_approved)

    @override_settings(FIXED_OTP_CODE="1234", FINIK_USE_STUB=False)
    def test_registration_checkout_dashboard_flow_no_sms_no_fake_payment(self):
        with patch("accounts.views._dispatch_task") as sms, patch("shop.views.create_payment", side_effect=PaymentGatewayError("Провайдер недоступен")):
            self.assertEqual(self.client.post("/accounts/register/", {"phone_number": "+996555887002"}).status_code, 302)
            self.assertEqual(self.client.post("/accounts/verify/", {"code": "1234"}).status_code, 302)
            self.assertEqual(self.client.get(self.product.get_absolute_url()).status_code, 200)
            self.client.post(f"/cart/add/{self.product.pk}/", {"quantity": 1})
            self.assertEqual(self.client.get("/checkout/").status_code, 200)
            response = self.client.post("/checkout/", {"country": "Кыргызстан", "city": "Бишкек", "street": "Тестовая", "building": "1", "payment_method": "qr"})
            self.assertEqual(response.status_code, 302)
            created = Order.objects.get(user__phone_number="+996555887002")
            self.assertEqual(created.payment_status, "waiting")
            self.use_role("Owner")
            self.assertContains(self.client.get("/dashboard/orders/"), created.order_number)
            sms.assert_not_called()

    def product_payload(self):
        return {
            "name": "Новый товар", "slug": "new-dashboard-product", "description": "Описание",
            "category": self.category.pk, "price": "1500.00", "is_active": "on",
            "gallery-TOTAL_FORMS": "0", "gallery-INITIAL_FORMS": "0",
            "wholesale-TOTAL_FORMS": "1", "wholesale-INITIAL_FORMS": "0",
            "wholesale-0-min_quantity": "9", "wholesale-0-price": "1000.00",
        }

    def test_product_creation_preserves_wholesale_semantics(self):
        self.use_role("Manager")
        self.assertEqual(self.client.post("/dashboard/products/new/", self.product_payload()).status_code, 302)
        product = Product.objects.get(slug="new-dashboard-product")
        self.assertEqual(product.stock, 0)
        self.assertEqual(product.get_price_for_quantity(9), 1500)
        self.assertEqual(product.get_price_for_quantity(10), 1000)

    def test_product_rejects_invalid_upload_and_negative_price(self):
        self.use_role("Manager")
        payload = self.product_payload()
        payload["image"] = SimpleUploadedFile("bad.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.client.post("/dashboard/products/new/", payload).status_code, 200)
        self.assertFalse(Product.objects.filter(slug=payload["slug"]).exists())
        payload = self.product_payload()
        payload["price"] = "-1"
        self.assertEqual(self.client.post("/dashboard/products/new/", payload).status_code, 200)

    def test_product_form_cannot_override_stock_or_payment(self):
        self.use_role("Manager")
        payload = self.product_payload()
        payload.update(slug=self.product.slug, stock=999, payment_status="success")
        self.assertEqual(self.client.post(f"/dashboard/products/{self.product.pk}/edit/", payload).status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)

    def test_admin_login_uses_dashboard_and_rejects_external_next(self):
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)
        response = self.client.post("/admin/login/?next=https://attacker.example/", {
            "username": "owner@example.test", "password": "SecurePassword456!",
        })
        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)

    def test_role_sync_is_idempotent(self):
        before = Group.objects.get(name="Manager").permissions.count()
        call_command("setup_dashboard_roles", verbosity=0)
        self.assertEqual(Group.objects.get(name="Manager").permissions.count(), before)

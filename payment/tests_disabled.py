from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.models import User
from accounts.tasks import send_admin_verification_email
from payment.models import PaymentEvent
from payment.services import PaymentGatewayError, create_payment, check_payment_status
from payment.tasks import reconcile_pending_payments, reconcile_pending_payments_task
from project.checks import production_configuration_check
from shop.models import Category, Order, Product


@override_settings(PAYMENT_ENABLED=False, FINIK_USE_STUB=False, FIXED_OTP_CODE="1234")
class DisabledPaymentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_client(phone_number="+996700889001")
        self.category = Category.objects.create(name="Каталог", slug="disabled-payments")
        self.product = Product.objects.create(name="Товар", slug="disabled-product", description="Описание",
                                              category=self.category, price=100, stock=10)
        self.order = Order.objects.create(user=self.user, total_price=100)
        self.client.force_login(self.user)

    def test_service_guards_precede_network_and_payment_id_assignment(self):
        with patch("payment.services.requests.post") as post, patch("payment.services.requests.get") as get:
            with self.assertRaises(PaymentGatewayError):
                create_payment(self.order)
            with self.assertRaises(PaymentGatewayError):
                check_payment_status("existing-real-payment")
            post.assert_not_called()
            get.assert_not_called()
        self.order.refresh_from_db()
        self.assertIsNone(self.order.payment_id)
        self.assertEqual(self.order.payment_status, "waiting")

    def test_both_reconciliation_entrypoints_skip(self):
        with patch("payment.tasks.check_payment_status") as check:
            self.assertEqual(reconcile_pending_payments_task(), {"skipped": "payment_disabled"})
            self.assertEqual(reconcile_pending_payments()["checked"], 0)
            check.assert_not_called()

    def test_webhook_rejected_without_mutation(self):
        with patch("payment.views.verify_request_signature") as verify:
            response = self.client.post("/webhook/finik/", {"status": "success"}, content_type="application/json")
            self.assertEqual(response.status_code, 503)
            verify.assert_not_called()
        self.assertFalse(PaymentEvent.objects.exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "waiting")

    @override_settings(FINIK_USE_STUB=True)
    def test_stub_cannot_bypass_disabled_payments(self):
        self.assertEqual(self.client.post("/pay/test/anything/").status_code, 404)

    def test_checkout_creates_unpaid_order_without_gateway(self):
        self.client.post(f"/cart/add/{self.product.pk}/", {"quantity": 2})
        self.assertContains(self.client.get("/checkout/"), "Онлайн-оплата временно недоступна")
        with patch("shop.views.create_payment") as gateway:
            response = self.client.post("/checkout/", {
                "country": "Кыргызстан", "city": "Бишкек", "street": "Тестовая", "building": "1", "payment_method": "qr",
            })
            gateway.assert_not_called()
        self.assertEqual(response.status_code, 302)
        order = Order.objects.exclude(pk=self.order.pk).get()
        self.assertEqual((order.status, order.payment_status), ("pending", "waiting"))
        self.assertIsNone(order.payment_id)
        self.assertIsNone(order.paid_at)
        self.assertEqual(order.total_price, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertContains(self.client.get(order.get_absolute_url()), "Онлайн-оплата временно недоступна")
        owner = User.objects.create_superuser(email="disabled-owner@example.test", password="TestPassword456!")
        self.client.force_login(owner)
        self.assertContains(self.client.get("/dashboard/orders/"), order.order_number)

    def test_existing_payment_link_hidden_and_retry_disabled(self):
        self.order.payment_link = "https://qr.finik.kg/previous-payment"
        self.order.qr_code = "data:image/png;base64,old"
        self.order.save()
        page = self.client.get(self.order.get_absolute_url())
        self.assertNotContains(page, self.order.payment_link)
        self.assertNotContains(page, self.order.qr_code)
        self.assertNotContains(page, "Создать ссылку оплаты")
        with patch("shop.views.create_payment") as gateway:
            self.client.post(f"/order/{self.order.order_number}/pay/")
            gateway.assert_not_called()

    @override_settings(ENVIRONMENT="production", FINIK_API_KEY="", FINIK_ACCOUNT_ID="", FINIK_PRIVATE_KEY="",
                       FINIK_WEBHOOK_PUBLIC_KEY="", FINIK_STATUS_API_URL="",
                       ADMIN_EMAIL_VERIFICATION_ENABLED=False,
                       EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                       EMAIL_HOST="", EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="")
    def test_production_checks_exempt_only_disabled_features(self):
        ids = {issue.id for issue in production_configuration_check(None)}
        self.assertFalse(ids & {"project.E015", "project.E016", "project.E019", "project.E020", "project.E029", "project.E028"})
        self.assertTrue({"project.W003", "project.W004"} <= ids)
        with override_settings(FINIK_USE_STUB=True, DEBUG=True, SESSION_COOKIE_SECURE=False):
            ids = {issue.id for issue in production_configuration_check(None)}
            self.assertTrue({"project.E018", "project.E001", "project.E008"} <= ids)
        with override_settings(PAYMENT_ENABLED=True, ADMIN_EMAIL_VERIFICATION_ENABLED=True):
            ids = {issue.id for issue in production_configuration_check(None)}
            self.assertTrue({"project.E019", "project.E029", "project.E028"} <= ids)
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            self.assertIn("project.E017", {issue.id for issue in production_configuration_check(None)})


@override_settings(ADMIN_EMAIL_VERIFICATION_ENABLED=False)
class DisabledAdminEmailTests(TestCase):
    def test_no_delivery_even_from_queued_task(self):
        with patch("accounts.tasks.send_mail") as send:
            self.assertEqual(send_admin_verification_email("test@example.test", "https://example.test/"), "admin-email-disabled")
            send.assert_not_called()

    def test_registration_and_verification_do_not_create_or_activate_admin(self):
        owner = User.objects.create_superuser(email="owner@example.test", password="TestPassword456!")
        self.client.force_login(owner)
        self.assertEqual(self.client.get("/accounts/admin/register/").status_code, 503)
        self.assertEqual(self.client.post("/accounts/admin/register/", {"email": "new@example.test"}).status_code, 503)
        self.assertEqual(self.client.get("/accounts/admin/verify/token/").status_code, 503)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)

    @override_settings(ADMIN_EMAIL_VERIFICATION_ENABLED=True)
    def test_reenabled_email_uses_existing_delivery(self):
        with patch("accounts.tasks.send_mail") as send:
            self.assertEqual(send_admin_verification_email("test@example.test", "https://example.test/"), "sent")
            send.assert_called_once()

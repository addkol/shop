import json
from decimal import Decimal
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from shop.models import Category, Order, OrderItem, Product
from shop.order_lifecycle import cancel_expired_orders

from .finik import current_timestamp_ms, sign_request
from .models import PaymentEvent
from .services import PaymentGatewayError, _validate_payment_link
from .tasks import purge_old_payment_payloads_task, reconcile_pending_payments_task


class FinikWebhookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        cls.public_key = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def setUp(self):
        self.user = get_user_model().objects.create_client(phone_number="+996700000010")
        self.category = Category.objects.create(name="Оплата", slug="payment-category")
        self.product = Product.objects.create(
            name="Товар для оплаты",
            slug="payment-product",
            description="Описание",
            price=Decimal("500.00"),
            stock=3,
            category=self.category,
        )
        self.order = Order.objects.create(
            user=self.user,
            total_price=Decimal("1000.00"),
            payment_id="payment-test-1",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            price=self.product.price,
            quantity=2,
        )

    def post_event(self, payload, signature_override=None):
        timestamp = current_timestamp_ms()
        signature = sign_request(
            "POST",
            reverse("payment:finik-webhook"),
            {"Host": "testserver", "x-api-timestamp": timestamp},
            payload,
            self.private_key,
        )
        return self.client.post(
            reverse("payment:finik-webhook"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_API_TIMESTAMP=timestamp,
            HTTP_SIGNATURE=signature_override or signature,
        )

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_valid_success_event_marks_order_paid(self):
        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            response = self.post_event(
                {
                    "transactionId": "event-success-1",
                    "status": "success",
                    "amount": "1000.00",
                    "fields": {"paymentId": self.order.payment_id},
                }
            )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCESS)
        self.assertEqual(PaymentEvent.objects.count(), 1)

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_duplicate_event_is_idempotent(self):
        payload = {
            "transactionId": "event-duplicate-1",
            "status": "success",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }
        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            first_response = self.post_event(payload)
            second_response = self.post_event(payload)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(PaymentEvent.objects.count(), 1)

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_invalid_signature_is_rejected(self):
        payload = {
            "transactionId": "event-invalid-1",
            "status": "success",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }
        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            response = self.post_event(payload, signature_override="invalid")

        self.assertEqual(response.status_code, 401)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.WAITING)
        self.assertFalse(PaymentEvent.objects.exists())

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_failed_event_releases_reserved_stock_once(self):
        payload = {
            "transactionId": "event-failed-1",
            "status": "failed",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }
        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(self.order.stock_released)
        self.assertEqual(self.product.stock, 5)

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_late_success_requires_refund_without_re_reserving_stock(self):
        self.order.status = Order.Status.CANCELLED
        self.order.payment_status = Order.PaymentStatus.FAILED
        self.order.stock_released = True
        self.order.save(update_fields=["status", "payment_status", "stock_released"])
        payload = {
            "transactionId": "event-late-success-1",
            "status": "success",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }

        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUND_REQUIRED)
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(
            PaymentEvent.objects.get().status,
            "late_success_refund_required",
        )

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_failed_event_after_success_does_not_cancel_paid_order(self):
        self.order.status = Order.Status.PAID
        self.order.payment_status = Order.PaymentStatus.SUCCESS
        self.order.save(update_fields=["status", "payment_status"])
        payload = {
            "transactionId": "event-failed-after-success-1",
            "status": "failed",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }

        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCESS)
        self.assertFalse(self.order.stock_released)
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(PaymentEvent.objects.get().status, "ignored_failed_after_success")

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_sensitive_payload_fields_are_redacted(self):
        payload = {
            "transactionId": "event-redacted-1",
            "status": "success",
            "amount": "1000.00",
            "fields": {
                "paymentId": self.order.payment_id,
                "phoneNumber": "+996700123456",
                "note": "safe",
            },
            "accessToken": "top-secret",
        }

        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        stored_payload = PaymentEvent.objects.get().payload
        self.assertEqual(stored_payload["fields"]["phoneNumber"], "[REDACTED]")
        self.assertEqual(stored_payload["accessToken"], "[REDACTED]")
        self.assertEqual(stored_payload["fields"]["note"], "safe")

    @override_settings(FINIK_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_unsupported_currency_is_rejected(self):
        with override_settings(FINIK_WEBHOOK_PUBLIC_KEY=self.public_key):
            response = self.post_event(
                {
                    "transactionId": "event-currency-1",
                    "status": "success",
                    "amount": "1000.00",
                    "currency": "USD",
                    "fields": {"paymentId": self.order.payment_id},
                }
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PaymentEvent.objects.exists())

    @override_settings(PAYMENT_WEBHOOK_MAX_BODY_BYTES=16)
    def test_oversized_webhook_is_rejected_before_parsing(self):
        response = self.client.post(
            reverse("payment:finik-webhook"),
            data=json.dumps({"payload": "x" * 100}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)


@override_settings(FINIK_USE_STUB=True)
class StubPaymentTests(TestCase):
    def test_stub_payment_is_available_only_to_order_owner(self):
        owner = get_user_model().objects.create_client(phone_number="+996700000020")
        stranger = get_user_model().objects.create_client(phone_number="+996700000021")
        order = Order.objects.create(
            user=owner,
            total_price=Decimal("100.00"),
            payment_id="stub-owner-payment",
        )
        self.client.force_login(stranger)

        response = self.client.get(
            reverse("payment:stub-payment", kwargs={"payment_id": order.payment_id})
        )

        self.assertEqual(response.status_code, 404)


class PaymentLinkSafetyTests(TestCase):
    @override_settings(FINIK_PAYMENT_URL_ALLOWED_HOSTS=["qr.finik.kg"])
    def test_allows_https_link_from_configured_provider(self):
        payment_link = "https://qr.finik.kg/payment/123"

        self.assertEqual(_validate_payment_link(payment_link), payment_link)

    @override_settings(FINIK_PAYMENT_URL_ALLOWED_HOSTS=["qr.finik.kg"])
    def test_rejects_untrusted_or_credentialed_link(self):
        for payment_link in (
            "http://qr.finik.kg/payment/123",
            "https://attacker.example/payment/123",
            "https://user:password@qr.finik.kg/payment/123",
        ):
            with self.subTest(payment_link=payment_link), self.assertRaises(PaymentGatewayError):
                _validate_payment_link(payment_link)


class PaymentPayloadRetentionTests(TestCase):
    def test_old_payload_is_purged_without_deleting_audit_event(self):
        event = PaymentEvent.objects.create(
            provider_event_id="retention-event",
            payment_id="retention-payment",
            status="success",
            payload={"phone": "+996700123456"},
            signature_valid=True,
        )
        PaymentEvent.objects.filter(pk=event.pk).update(
            received_at=timezone.now() - timezone.timedelta(days=400)
        )

        with override_settings(PAYMENT_EVENT_PAYLOAD_RETENTION_DAYS=365):
            updated = purge_old_payment_payloads_task()

        event.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertEqual(event.payload, {})

    def test_dry_run_does_not_clear_payload(self):
        event = PaymentEvent.objects.create(
            provider_event_id="retention-dry-run",
            payment_id="retention-payment-dry-run",
            status="success",
            payload={"safe": "value"},
            signature_valid=True,
        )
        PaymentEvent.objects.filter(pk=event.pk).update(
            received_at=timezone.now() - timezone.timedelta(days=400)
        )

        with override_settings(PAYMENT_EVENT_PAYLOAD_RETENTION_DAYS=365):
            matched = purge_old_payment_payloads_task(dry_run=True)

        event.refresh_from_db()
        self.assertEqual(matched, 1)
        self.assertEqual(event.payload, {"safe": "value"})


@override_settings(
    FINIK_USE_STUB=False,
    FINIK_RECONCILIATION_MIN_AGE_SECONDS=0,
    FINIK_RECONCILIATION_BATCH_SIZE=100,
    FINIK_RECONCILIATION_LOOKBACK_HOURS=72,
)
class PaymentReconciliationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_client(phone_number="+996700000030")
        self.category = Category.objects.create(name="Сверка", slug="reconciliation-category")
        self.product = Product.objects.create(
            name="Товар для сверки",
            slug="reconciliation-product",
            description="Описание",
            price=Decimal("500.00"),
            stock=3,
            category=self.category,
        )
        self.order = Order.objects.create(
            user=self.user,
            total_price=Decimal("1000.00"),
            payment_id="reconciliation-payment-1",
            payment_expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            price=self.product.price,
            quantity=2,
        )

    @patch("payment.tasks.check_payment_status")
    def test_confirmed_success_marks_order_paid(self, check_status):
        check_status.return_value = {
            "transactionId": "reconcile-success-1",
            "status": "SUCCEEDED",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }

        stats = reconcile_pending_payments_task()

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCESS)
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(PaymentEvent.objects.get().provider_event_id, "reconcile-success-1")

    @patch("payment.tasks.check_payment_status")
    def test_pending_status_never_marks_order_paid(self, check_status):
        check_status.return_value = {
            "status": "PROCESSING",
            "fields": {"paymentId": self.order.payment_id},
        }

        stats = reconcile_pending_payments_task()

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.WAITING)
        self.assertIsNotNone(self.order.payment_checked_at)
        self.assertEqual(stats["pending"], 1)
        self.assertFalse(PaymentEvent.objects.exists())

    @patch("payment.tasks.check_payment_status")
    def test_gateway_timeout_leaves_order_waiting(self, check_status):
        check_status.side_effect = PaymentGatewayError("timeout")

        stats = reconcile_pending_payments_task()

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.WAITING)
        self.assertEqual(self.order.payment_reconciliation_failures, 1)
        self.assertEqual(stats["errors"], 1)

    @patch("payment.tasks.check_payment_status")
    def test_duplicate_terminal_status_is_idempotent(self, check_status):
        check_status.return_value = {
            "transactionId": "reconcile-duplicate-1",
            "status": "SUCCEEDED",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }

        reconcile_pending_payments_task()
        reconcile_pending_payments_task()

        self.assertEqual(PaymentEvent.objects.count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCESS)

    @patch("payment.tasks.check_payment_status")
    def test_late_confirmed_success_requires_refund(self, check_status):
        self.order.status = Order.Status.CANCELLED
        self.order.payment_status = Order.PaymentStatus.FAILED
        self.order.stock_released = True
        self.order.cancelled_at = timezone.now()
        self.order.save(
            update_fields=["status", "payment_status", "stock_released", "cancelled_at"]
        )
        check_status.return_value = {
            "transactionId": "reconcile-late-success-1",
            "status": "SUCCEEDED",
            "amount": "1000.00",
            "fields": {"paymentId": self.order.payment_id},
        }

        reconcile_pending_payments_task()

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUND_REQUIRED)

    def test_expired_real_payment_waits_for_successful_provider_check(self):
        self.order.payment_expires_at = timezone.now() - timezone.timedelta(minutes=1)
        self.order.save(update_fields=["payment_expires_at"])

        self.assertEqual(cancel_expired_orders(), 0)
        self.order.payment_checked_at = timezone.now()
        self.order.payment_reconciliation_failures = 0
        self.order.save(
            update_fields=["payment_checked_at", "payment_reconciliation_failures"]
        )

        self.assertEqual(cancel_expired_orders(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)

    @patch("payment.tasks.check_payment_status")
    @patch("payment.tasks.timezone.now")
    def test_unconfirmed_or_invalid_success_never_pays_order(self, now, check_status):
        now.return_value = self.order.created_at + timezone.timedelta(minutes=1)
        for index, overrides in enumerate([
            {"amount": None}, {"amount": "NaN"}, {"amount": "Infinity"},
            {"amount": "999.00"}, {"currency": "USD"},
            {"fields": {"paymentId": "another-payment"}}, {"fields": {}},
            {"status": "unknown"},
        ]):
            with self.subTest(overrides=overrides):
                check_status.return_value = {
                    "transactionId": f"invalid-success-{index}", "status": "SUCCEEDED",
                    "amount": "1000.00", "fields": {"paymentId": self.order.payment_id},
                    **overrides,
                }
                stats = reconcile_pending_payments_task()
                self.order.refresh_from_db()
                self.assertEqual(self.order.payment_status, Order.PaymentStatus.WAITING)
                self.assertFalse(self.order.stock_released)
                self.assertEqual(stats["errors"], 1)

    @patch("payment.tasks.check_payment_status")
    def test_failed_poll_releases_stock_only_once(self, check_status):
        check_status.return_value = {
            "transactionId": "polled-failure", "status": "FAILED",
            "fields": {"paymentId": self.order.payment_id},
        }
        reconcile_pending_payments_task()
        reconcile_pending_payments_task()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(PaymentEvent.objects.filter(provider_event_id="polled-failure").count(), 1)

    @patch("payment.tasks.check_payment_status")
    def test_webhook_success_during_poll_is_preserved(self, check_status):
        def provider_response(payment_id):
            Order.objects.filter(pk=self.order.pk).update(
                status=Order.Status.PAID, payment_status=Order.PaymentStatus.SUCCESS,
            )
            return {"status": "FAILED", "fields": {"paymentId": payment_id}}
        check_status.side_effect = provider_response
        reconcile_pending_payments_task()
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCESS)
        self.assertFalse(self.order.stock_released)

    @override_settings(FINIK_USE_STUB=True)
    @patch("payment.tasks.check_payment_status")
    def test_stub_never_calls_real_provider(self, check_status):
        reconcile_pending_payments_task()
        check_status.assert_not_called()

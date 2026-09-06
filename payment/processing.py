from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from shop.models import Order
from shop.services import release_order_stock

from .models import PaymentEvent
from .services import mark_order_paid


SUCCESS_STATUSES = {"success", "succeeded"}
FAILED_STATUSES = {"failed", "canceled", "cancelled"}
PENDING_STATUSES = {"pending", "processing", "waiting"}
SENSITIVE_PAYLOAD_FRAGMENTS = (
    "phone",
    "email",
    "token",
    "secret",
    "card",
    "authorization",
)


class ProviderPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderPaymentStatus:
    payment_id: str
    event_id: str
    status: str
    amount: Decimal | None
    currency: str

    @property
    def is_terminal(self):
        return self.status in SUCCESS_STATUSES | FAILED_STATUSES


@dataclass(frozen=True)
class PaymentProcessingResult:
    outcome: str
    order_number: str = ""
    duplicate: bool = False


def redact_payload(value):
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(fragment in key.lower() for fragment in SENSITIVE_PAYLOAD_FRAGMENTS)
                else redact_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value


def normalize_provider_payload(payload, expected_payment_id=None, require_event_id=False):
    if not isinstance(payload, dict):
        raise ProviderPayloadError("Finik вернул некорректный формат ответа.")

    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    data = payload.get("Data") if isinstance(payload.get("Data"), dict) else {}
    returned_payment_id = (
        fields.get("paymentId")
        or data.get("paymentId")
        or payload.get("payment_id")
        or payload.get("PaymentId")
    )
    if returned_payment_id and expected_payment_id and str(returned_payment_id) != str(expected_payment_id):
        raise ProviderPayloadError("Finik вернул статус другого платежа.")

    payment_id = str(returned_payment_id or expected_payment_id or "").strip()
    event_id = str(payload.get("transactionId") or payload.get("id") or "").strip()
    status = str(payload.get("status", "")).strip().lower()
    if status in SUCCESS_STATUSES and expected_payment_id and not returned_payment_id:
        raise ProviderPayloadError("Finik не подтвердил идентификатор успешного платежа.")
    currency = str(payload.get("currency") or fields.get("currency") or "").strip().upper()
    raw_amount = payload.get("amount")
    if raw_amount is None:
        raw_amount = payload.get("Amount")
    if raw_amount is None:
        raw_amount = fields.get("amount")

    if not payment_id:
        raise ProviderPayloadError("Finik не вернул идентификатор платежа.")
    if len(payment_id) > 128:
        raise ProviderPayloadError("Идентификатор платежа Finik слишком длинный.")
    if require_event_id and not event_id:
        raise ProviderPayloadError("Finik не вернул идентификатор события.")
    if len(event_id) > 160:
        raise ProviderPayloadError("Идентификатор события Finik слишком длинный.")
    if status not in SUCCESS_STATUSES | FAILED_STATUSES | PENDING_STATUSES:
        raise ProviderPayloadError("Finik вернул неизвестный статус платежа.")
    if currency and currency != "KGS":
        raise ProviderPayloadError("Валюта платежа Finik не поддерживается.")

    amount = None
    if raw_amount is not None:
        try:
            amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
            if not amount.is_finite() or amount < 0:
                raise ValueError("Invalid amount")
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ProviderPayloadError("Finik вернул некорректную сумму платежа.") from exc
    if status in SUCCESS_STATUSES and amount is None:
        raise ProviderPayloadError("Finik не подтвердил сумму успешного платежа.")

    return ProviderPaymentStatus(
        payment_id=payment_id,
        event_id=event_id,
        status=status,
        amount=amount,
        currency=currency,
    )


def apply_terminal_payment_status(provider_status, payload, signature_valid):
    if not provider_status.is_terminal:
        raise ProviderPayloadError("Промежуточный статус нельзя применить как финальный.")

    event_id = provider_status.event_id or (
        f"reconcile:{provider_status.payment_id}:{provider_status.status}"
    )
    with transaction.atomic():
        if PaymentEvent.objects.select_for_update().filter(provider_event_id=event_id).exists():
            return PaymentProcessingResult(outcome="duplicate", duplicate=True)

        order = (
            Order.objects.select_for_update()
            .prefetch_related("items")
            .get(payment_id=provider_status.payment_id)
        )
        event = PaymentEvent.objects.create(
            order=order,
            provider_event_id=event_id,
            payment_id=provider_status.payment_id,
            status=provider_status.status,
            amount=provider_status.amount,
            payload=redact_payload(payload),
            signature_valid=signature_valid,
        )

        if provider_status.amount is not None and provider_status.amount != order.total_price:
            event.status = "amount_mismatch"
            order.payment_last_error = "Сумма Finik не совпадает с суммой заказа."
            order.save(update_fields=["payment_last_error", "updated_at"])
            outcome = event.status
        elif provider_status.status in SUCCESS_STATUSES:
            if order.stock_released or order.status == Order.Status.CANCELLED:
                event.status = "late_success_refund_required"
                order.payment_status = Order.PaymentStatus.REFUND_REQUIRED
                order.paid_at = timezone.now()
                order.payment_last_error = (
                    "Оплата поступила после отмены заказа. Требуется возврат покупателю."
                )
                order.save(
                    update_fields=[
                        "payment_status",
                        "paid_at",
                        "payment_last_error",
                        "updated_at",
                    ]
                )
                outcome = event.status
            else:
                mark_order_paid(order)
                outcome = "success"
        elif order.payment_status in {Order.PaymentStatus.SUCCESS, Order.PaymentStatus.REFUND_REQUIRED} or order.status in {
            Order.Status.PAID,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        }:
            event.status = "ignored_failed_after_success"
            outcome = event.status
        else:
            release_order_stock(order, "Платёж отклонён платёжной системой.")
            outcome = provider_status.status

        event.processed_at = timezone.now()
        event.save(update_fields=["status", "processed_at"])
        return PaymentProcessingResult(outcome=outcome, order_number=order.order_number)

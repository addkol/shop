from datetime import timedelta
import logging
from contextlib import contextmanager

from celery import shared_task
from django.conf import settings
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from shop.models import Order

from .models import PaymentEvent
from .processing import (
    ProviderPayloadError,
    apply_terminal_payment_status,
    normalize_provider_payload,
)
from .services import PaymentGatewayError, check_payment_status


logger = logging.getLogger("payment.finik")


@contextmanager
def reconciliation_lock():
    if connection.vendor != "postgresql":
        yield True
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [76293841])
        acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [76293841])


def _record_reconciliation_error(order_id, checked_at, message):
    return Order.objects.filter(pk=order_id).filter(
        Q(payment_checked_at__isnull=True) | Q(payment_checked_at__lte=checked_at)
    ).filter(
        Q(payment_status=Order.PaymentStatus.WAITING)
        | Q(payment_status=Order.PaymentStatus.FAILED, status=Order.Status.CANCELLED)
    ).update(
        payment_checked_at=checked_at,
        payment_reconciliation_failures=F("payment_reconciliation_failures") + 1,
        payment_last_error=str(message)[:2000],
        updated_at=checked_at,
    )


@shared_task(
    autoretry_for=(DatabaseError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=300,
    time_limit=330,
)
def reconcile_pending_payments_task(limit=None):
    with reconciliation_lock() as acquired:
        if not acquired:
            return {"skipped": "already_running"}
        return reconcile_pending_payments(limit)


def reconcile_pending_payments(limit=None):
    stats = {"checked": 0, "pending": 0, "processed": 0, "duplicates": 0, "errors": 0}
    if settings.FINIK_USE_STUB:
        return stats

    now = timezone.now()
    batch_size = min(
        max(int(limit or settings.FINIK_RECONCILIATION_BATCH_SIZE), 1),
        settings.FINIK_RECONCILIATION_BATCH_SIZE,
    )
    new_payment_cutoff = now - timedelta(seconds=settings.FINIK_RECONCILIATION_MIN_AGE_SECONDS)
    cancelled_cutoff = now - timedelta(hours=settings.FINIK_RECONCILIATION_LOOKBACK_HOURS)
    candidates = list(
        Order.objects.filter(payment_id__isnull=False, created_at__lte=new_payment_cutoff)
        .exclude(payment_id="")
        .filter(
            Q(
                status=Order.Status.PENDING,
                payment_status=Order.PaymentStatus.WAITING,
                stock_released=False,
            )
            | Q(
                status=Order.Status.CANCELLED,
                payment_status=Order.PaymentStatus.FAILED,
                stock_released=True,
                cancelled_at__gte=cancelled_cutoff,
            )
        )
        .order_by(F("payment_checked_at").asc(nulls_first=True), "created_at")
        .values("pk", "payment_id")[:batch_size]
    )

    for candidate in candidates:
        checked_at = timezone.now()
        try:
            payload = check_payment_status(candidate["payment_id"])
            provider_status = normalize_provider_payload(
                payload,
                expected_payment_id=candidate["payment_id"],
            )
        except (PaymentGatewayError, ProviderPayloadError) as exc:
            _record_reconciliation_error(candidate["pk"], checked_at, exc)
            logger.warning(
                "Не удалось сверить платёж %s с Finik: %s",
                candidate["payment_id"],
                exc,
            )
            stats["errors"] += 1
            continue

        stats["checked"] += 1
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=candidate["pk"])
                if order.payment_id != candidate["payment_id"] or order.payment_status in {
                    Order.PaymentStatus.SUCCESS, Order.PaymentStatus.REFUND_REQUIRED,
                }:
                    continue
                if order.payment_checked_at and order.payment_checked_at > checked_at:
                    continue
                if not provider_status.is_terminal:
                    order.payment_checked_at = checked_at
                    order.payment_reconciliation_failures = 0
                    order.payment_last_error = ""
                    order.save(update_fields=[
                        "payment_checked_at", "payment_reconciliation_failures",
                        "payment_last_error", "updated_at",
                    ])
                    stats["pending"] += 1
                    continue
                result = apply_terminal_payment_status(provider_status, payload, signature_valid=False)
                if not result.duplicate and result.outcome != "amount_mismatch":
                    Order.objects.filter(pk=order.pk).update(
                        payment_checked_at=checked_at, payment_reconciliation_failures=0,
                    )
                elif result.outcome == "amount_mismatch":
                    _record_reconciliation_error(order.pk, checked_at, "Сумма Finik не совпадает с суммой заказа.")
        except Order.DoesNotExist:
            continue
        except IntegrityError:
            stats["duplicates"] += 1
            continue

        if result.duplicate:
            stats["duplicates"] += 1
        elif result.outcome == "amount_mismatch":
            logger.error(
                "Сверка Finik обнаружила несовпадение суммы платежа %s",
                candidate["payment_id"],
            )
            stats["errors"] += 1
        else:
            stats["processed"] += 1
    return stats


@shared_task
def purge_old_payment_payloads_task(dry_run=False):
    cutoff = timezone.now() - timedelta(days=settings.PAYMENT_EVENT_PAYLOAD_RETENTION_DAYS)
    queryset = PaymentEvent.objects.filter(received_at__lt=cutoff).exclude(payload={})
    if dry_run:
        return queryset.count()
    return queryset.update(payload={})

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import Order
from .services import release_order_stock


@transaction.atomic
def transition_order(order_id, action, reason=""):
    order = Order.objects.select_for_update().get(pk=order_id)
    if action == "cancel":
        if not order.can_be_cancelled or not reason.strip():
            raise ValidationError("Этот заказ нельзя отменить либо не указана причина.")
        release_order_stock(order, reason.strip())
    elif action == "ship" and order.status == Order.Status.PAID and order.payment_status == Order.PaymentStatus.SUCCESS and not order.stock_released:
        order.status = Order.Status.SHIPPED
        order.save(update_fields=["status", "updated_at"])
    elif action == "deliver" and order.status == Order.Status.SHIPPED and order.payment_status == Order.PaymentStatus.SUCCESS and not order.stock_released:
        order.status = Order.Status.DELIVERED
        order.save(update_fields=["status", "updated_at"])
    else:
        raise ValidationError("Переход недоступен для текущего состояния заказа.")
    return order


def cancel_expired_orders(limit=200):
    queryset = Order.objects.filter(
        status=Order.Status.PENDING,
        payment_status=Order.PaymentStatus.WAITING,
        payment_expires_at__lte=timezone.now(),
        stock_released=False,
    )
    if not settings.FINIK_USE_STUB:
        queryset = queryset.filter(
            Q(payment_id__isnull=True)
            | Q(payment_id="")
            | Q(
                payment_checked_at__gte=F("payment_expires_at"),
                payment_reconciliation_failures=0,
            )
        )
    order_ids = list(queryset.order_by("payment_expires_at").values_list("pk", flat=True)[:limit])
    cancelled = 0
    for order_id in order_ids:
        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .prefetch_related("items")
                .filter(
                    pk=order_id,
                    status=Order.Status.PENDING,
                    payment_status=Order.PaymentStatus.WAITING,
                    stock_released=False,
                )
                .first()
            )
            if order and not settings.FINIK_USE_STUB and order.payment_id:
                if (
                    not order.payment_checked_at
                    or order.payment_checked_at < order.payment_expires_at
                    or order.payment_reconciliation_failures
                ):
                    continue
            if order and release_order_stock(order, "Истёк срок резервирования и оплаты заказа."):
                cancelled += 1
    return cancelled

from django.db.models import F
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Order, Product


@transaction.atomic
def adjust_product_stock(product_id, quantity, expected_stock):
    product = Product.objects.select_for_update().get(pk=product_id)
    if quantity < 0:
        raise ValidationError("Остаток не может быть отрицательным.")
    if product.stock != expected_stock:
        raise ValidationError("Остаток изменился. Обновите страницу и повторите корректировку.")
    product.stock = quantity
    product.full_clean()
    product.save(update_fields=["stock", "updated_at"])
    return product


def release_order_stock(order, reason, payment_failed=True):
    if order.stock_released:
        return False

    product_quantities = {}
    for item in order.items.all():
        if item.product_id:
            product_quantities[item.product_id] = product_quantities.get(item.product_id, 0) + item.quantity

    products = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=sorted(product_quantities))
    }
    for product_id, quantity in product_quantities.items():
        product = products.get(product_id)
        if product:
            Product.objects.filter(pk=product_id).update(stock=F("stock") + quantity, updated_at=timezone.now())

    order.status = Order.Status.CANCELLED
    if payment_failed:
        order.payment_status = Order.PaymentStatus.FAILED
    order.cancellation_reason = reason
    order.cancelled_at = timezone.now()
    order.stock_released = True
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "cancellation_reason",
            "cancelled_at",
            "stock_released",
            "updated_at",
        ]
    )
    return True

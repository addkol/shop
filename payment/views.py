import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from shop.models import Order


logger = logging.getLogger("payment.finik")


@csrf_exempt
@require_POST
def finik_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else request.POST.dict()
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON."}, status=400)

    payment_id = payload.get("payment_id")
    status = payload.get("status")
    if not payment_id or not status:
        return JsonResponse({"detail": "payment_id and status are required."}, status=400)

    try:
        order = Order.objects.get(payment_id=payment_id)
    except Order.DoesNotExist:
        logger.warning("Webhook for unknown payment_id=%s", payment_id)
        return JsonResponse({"detail": "Заказ не найден."}, status=404)

    if status == "success":
        order.payment_status = Order.PaymentStatus.SUCCESS
        order.status = Order.Status.PAID
    elif status == "failed":
        order.payment_status = Order.PaymentStatus.FAILED
        order.status = Order.Status.CANCELLED
    else:
        order.payment_status = Order.PaymentStatus.WAITING

    order.save(update_fields=["payment_status", "status", "updated_at"])
    logger.info("Webhook updated order %s to payment status %s", order.order_number, status)
    return JsonResponse({"detail": "ok"})

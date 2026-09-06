import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from shop.models import Order
from .finik import timestamp_is_fresh, verify_request_signature
from .models import PaymentEvent
from .processing import (
    ProviderPayloadError,
    apply_terminal_payment_status,
    normalize_provider_payload,
)
from .services import mark_order_paid


logger = logging.getLogger("payment.finik")


def _request_signing_headers(request):
    headers = {"Host": request.get_host()}
    for key, value in request.headers.items():
        if key.lower().startswith("x-api-"):
            headers[key.lower()] = value
    return headers


@csrf_exempt
@require_POST
def finik_webhook(request):
    if not settings.PAYMENT_ENABLED:
        return JsonResponse({"detail": "Онлайн-оплата временно недоступна."}, status=503)
    if len(request.body) > settings.PAYMENT_WEBHOOK_MAX_BODY_BYTES:
        return JsonResponse({"detail": "Тело webhook слишком большое."}, status=413)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"detail": "Некорректный JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"detail": "Требуется JSON объект."}, status=400)

    signature = request.headers.get("signature", "")
    timestamp = request.headers.get("x-api-timestamp", "")
    if not settings.FINIK_WEBHOOK_PUBLIC_KEY:
        logger.error("Не настроен публичный ключ webhook Finik.")
        return JsonResponse({"detail": "Webhook временно не настроен."}, status=503)
    if not timestamp_is_fresh(timestamp, settings.FINIK_WEBHOOK_TOLERANCE_SECONDS):
        return JsonResponse({"detail": "Временная метка webhook недействительна."}, status=401)
    if not verify_request_signature(
        request.method,
        request.path,
        _request_signing_headers(request),
        payload,
        settings.FINIK_WEBHOOK_PUBLIC_KEY,
        signature,
        query_params=request.GET.dict(),
    ):
        logger.warning("Отклонён webhook Finik с недействительной подписью.")
        return JsonResponse({"detail": "Недействительная подпись."}, status=401)

    try:
        provider_status = normalize_provider_payload(payload, require_event_id=True)
        if not provider_status.is_terminal:
            raise ProviderPayloadError("Webhook не содержит финальный статус платежа.")
    except ProviderPayloadError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    try:
        result = apply_terminal_payment_status(provider_status, payload, signature_valid=True)
    except IntegrityError:
        return JsonResponse({"detail": "Событие уже обработано."})
    except Order.DoesNotExist:
        logger.warning("Webhook для неизвестного идентификатора платежа.")
        return JsonResponse({"detail": "Заказ не найден."}, status=404)

    if result.duplicate:
        return JsonResponse({"detail": "Событие уже обработано."})
    if result.outcome == "amount_mismatch":
        logger.error("Сумма webhook не совпала с суммой заказа %s", result.order_number)
        return JsonResponse({"detail": "Сумма платежа не совпадает с заказом."}, status=400)
    if result.outcome == "late_success_refund_required":
        logger.error("Поздняя оплата отменённого заказа %s", result.order_number)
    elif result.outcome == "ignored_failed_after_success":
        logger.warning("Проигнорирован failed webhook после оплаты заказа %s", result.order_number)
    logger.info(
        "Webhook обновил заказ %s, статус %s",
        result.order_number,
        provider_status.status,
    )
    return JsonResponse({"detail": "Событие обработано."})


@login_required
def stub_payment(request, payment_id):
    if not settings.PAYMENT_ENABLED or not settings.FINIK_USE_STUB:
        raise Http404
    order = get_object_or_404(Order, payment_id=payment_id, user=request.user)
    if request.method == "POST":
        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), pk=order.pk, user=request.user)
            if order.can_be_paid:
                mark_order_paid(order)
                PaymentEvent.objects.get_or_create(
                    provider_event_id=f"stub-{order.payment_id}",
                    defaults={
                        "order": order,
                        "payment_id": order.payment_id,
                        "status": "success",
                        "amount": order.total_price,
                        "payload": {"source": "local_stub"},
                        "signature_valid": True,
                        "processed_at": timezone.now(),
                    },
                )
                messages.success(request, "Тестовая оплата успешно завершена.")
        return redirect(order.get_absolute_url())
    return render(request, "payment_stub.html", {"order": order})

import base64
import io
import logging
from decimal import Decimal

import qrcode
import requests
from django.conf import settings
from django.urls import reverse


logger = logging.getLogger("payment.finik")


class PaymentGatewayError(Exception):
    pass


def _absolute_url(request, route_name, **kwargs):
    path = reverse(route_name, kwargs=kwargs)
    if request is not None:
        return request.build_absolute_uri(path)
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def generate_qr(payment_url):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payment_url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def create_payment(order, request=None):
    callback_url = _absolute_url(request, "payment:finik-webhook")
    success_url = _absolute_url(request, "shop:order-success", order_number=order.order_number)
    fail_url = _absolute_url(request, "shop:cart")

    payload = {
        "amount": str(Decimal(order.total_price).quantize(Decimal("0.01"))),
        "currency": "KGS",
        "order_id": order.order_number,
        "callback_url": callback_url,
        "success_url": success_url,
        "fail_url": fail_url,
    }

    if settings.FINIK_USE_STUB or not settings.FINIK_API_KEY:
        payment_id = f"stub-{order.order_number.lower()}"
        payment_link = f"{settings.SITE_URL.rstrip('/')}/pay/{payment_id}/"
        qr_code = generate_qr(payment_link)
        order.payment_id = payment_id
        order.payment_link = payment_link
        order.qr_code = qr_code
        order.save(update_fields=["payment_id", "payment_link", "qr_code", "updated_at"])
        logger.info("Created stub Finik payment for order %s", order.order_number)
        return {"payment_id": payment_id, "payment_link": payment_link, "qr_code": qr_code}

    headers = {
        "Authorization": f"Bearer {settings.FINIK_API_KEY}",
        "Content-Type": "application/json",
    }
    logger.info("Creating Finik payment for order %s", order.order_number)

    try:
        response = requests.post(
            settings.FINIK_API_URL,
            json=payload,
            headers=headers,
            timeout=settings.FINIK_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Finik payment creation failed for order %s", order.order_number)
        raise PaymentGatewayError("Платёжный шлюз недоступен.") from exc

    data = response.json()
    payment_id = data.get("payment_id") or data.get("id")
    payment_link = data.get("qr_code_url") or data.get("payment_url") or data.get("link")
    if not payment_id or not payment_link:
        logger.error("Unexpected Finik response for order %s: %s", order.order_number, data)
        raise PaymentGatewayError("Платёжный шлюз вернул неожиданный ответ.")

    qr_code = generate_qr(payment_link)
    order.payment_id = payment_id
    order.payment_link = payment_link
    order.qr_code = qr_code
    order.save(update_fields=["payment_id", "payment_link", "qr_code", "updated_at"])
    logger.info("Created Finik payment %s for order %s", payment_id, order.order_number)
    return {"payment_id": payment_id, "payment_link": payment_link, "qr_code": qr_code}


def check_payment_status(payment_id):
    if settings.FINIK_USE_STUB or not settings.FINIK_API_KEY:
        return {"payment_id": payment_id, "status": "waiting"}

    headers = {"Authorization": f"Bearer {settings.FINIK_API_KEY}"}
    try:
        response = requests.get(
            f"{settings.FINIK_API_URL.rstrip('/')}/{payment_id}",
            headers=headers,
            timeout=settings.FINIK_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Finik status check failed for payment %s", payment_id)
        raise PaymentGatewayError("Не удалось проверить статус платежа.") from exc
    return response.json()

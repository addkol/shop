import base64
import io
import logging
import uuid
from decimal import Decimal
from urllib.parse import parse_qsl, quote, urlparse

import qrcode
import requests
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .finik import current_timestamp_ms, sign_request


logger = logging.getLogger("payment.finik")


class PaymentGatewayError(Exception):
    pass


def _payment_host_allowed(hostname):
    hostname = (hostname or "").lower().rstrip(".")
    for allowed_host in settings.FINIK_PAYMENT_URL_ALLOWED_HOSTS:
        allowed_host = allowed_host.lower().strip().rstrip(".")
        if allowed_host.startswith("*."):
            suffix = allowed_host[2:]
            if hostname == suffix or hostname.endswith(f".{suffix}"):
                return True
        elif hostname == allowed_host:
            return True
    return False


def _validate_payment_link(payment_link):
    payment_link = (payment_link or "").strip()
    parsed = urlparse(payment_link)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or not _payment_host_allowed(parsed.hostname)
    ):
        raise PaymentGatewayError("Платёжный шлюз вернул небезопасную ссылку.")
    return payment_link


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


def _save_payment_result(order, payment_id, payment_link):
    order.payment_id = payment_id
    order.payment_link = payment_link
    order.qr_code = generate_qr(payment_link)
    order.payment_attempts += 1
    order.payment_last_error = ""
    order.save(
        update_fields=[
            "payment_id",
            "payment_link",
            "qr_code",
            "payment_attempts",
            "payment_last_error",
            "updated_at",
        ]
    )
    return {
        "payment_id": payment_id,
        "payment_link": payment_link,
        "qr_code": order.qr_code,
    }


def record_payment_error(order, message):
    order.payment_attempts += 1
    order.payment_last_error = str(message)
    order.save(update_fields=["payment_attempts", "payment_last_error", "updated_at"])


def create_payment(order, request=None):
    if not order.can_be_paid:
        raise PaymentGatewayError("Этот заказ уже нельзя оплатить.")

    if not order.payment_id:
        candidate_payment_id = str(uuid.uuid4())
        assigned = order.__class__.objects.filter(pk=order.pk, payment_id__isnull=True).update(
            payment_id=candidate_payment_id
        )
        if assigned:
            order.payment_id = candidate_payment_id
        else:
            order.refresh_from_db(fields=["payment_id"])
    payment_id = order.payment_id
    if settings.FINIK_USE_STUB:
        payment_link = _absolute_url(request, "payment:stub-payment", payment_id=payment_id)
        result = _save_payment_result(order, payment_id, payment_link)
        logger.info("Создан тестовый платёж для заказа %s", order.order_number)
        return result

    required_settings = {
        "FINIK_API_KEY": settings.FINIK_API_KEY,
        "FINIK_ACCOUNT_ID": settings.FINIK_ACCOUNT_ID,
        "FINIK_PRIVATE_KEY": settings.FINIK_PRIVATE_KEY,
    }
    missing = [name for name, value in required_settings.items() if not value]
    if missing:
        raise PaymentGatewayError(f"Не настроены параметры Finik: {', '.join(missing)}.")

    callback_url = _absolute_url(request, "payment:finik-webhook")
    success_url = _absolute_url(request, "shop:order-success", order_number=order.order_number)
    payload = {
        "Amount": float(Decimal(order.total_price).quantize(Decimal("0.01"))),
        "CardType": "FINIK_QR",
        "PaymentId": payment_id,
        "RedirectUrl": success_url,
        "Data": {
            "accountId": settings.FINIK_ACCOUNT_ID,
            "name_en": settings.FINIK_DISPLAY_NAME,
            "webhookUrl": callback_url,
            "description": f"Заказ {order.order_number}",
            "Lang": "ru",
        },
    }
    if order.payment_expires_at:
        payload["Data"]["endDate"] = int(order.payment_expires_at.timestamp() * 1000)

    parsed_url = urlparse(settings.FINIK_API_URL)
    timestamp = current_timestamp_ms()
    signing_headers = {
        "Host": parsed_url.netloc,
        "x-api-key": settings.FINIK_API_KEY,
        "x-api-timestamp": timestamp,
    }
    signature = sign_request(
        "POST",
        parsed_url.path,
        signing_headers,
        payload,
        settings.FINIK_PRIVATE_KEY,
    )
    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.FINIK_API_KEY,
        "x-api-timestamp": timestamp,
        "signature": signature,
    }

    logger.info("Создание платежа Finik для заказа %s", order.order_number)
    try:
        response = requests.post(
            settings.FINIK_API_URL,
            json=payload,
            headers=headers,
            timeout=settings.FINIK_TIMEOUT,
            allow_redirects=False,
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            payment_link = response.headers.get("Location")
        else:
            response.raise_for_status()
            data = response.json()
            payment_link = data.get("paymentUrl") or data.get("payment_url") or data.get("link")
    except (requests.RequestException, ValueError) as exc:
        logger.exception("Ошибка создания платежа Finik для заказа %s", order.order_number)
        record_payment_error(order, "Платёжный шлюз временно недоступен.")
        raise PaymentGatewayError("Платёжный шлюз временно недоступен. Повторите оплату позже.") from exc

    if not payment_link:
        record_payment_error(order, "Finik не вернул ссылку на оплату.")
        raise PaymentGatewayError("Finik не вернул ссылку на оплату.")

    try:
        payment_link = _validate_payment_link(payment_link)
    except PaymentGatewayError as exc:
        record_payment_error(order, str(exc))
        raise
    return _save_payment_result(order, payment_id, payment_link)


def mark_order_paid(order):
    if order.payment_status == order.PaymentStatus.SUCCESS:
        return False
    order.payment_status = order.PaymentStatus.SUCCESS
    order.status = order.Status.PAID
    order.paid_at = timezone.now()
    order.payment_last_error = ""
    order.save(
        update_fields=["payment_status", "status", "paid_at", "payment_last_error", "updated_at"]
    )
    return True


def check_payment_status(payment_id):
    if settings.FINIK_USE_STUB:
        return {"payment_id": payment_id, "status": "waiting"}

    required_settings = {
        "FINIK_API_KEY": settings.FINIK_API_KEY,
        "FINIK_PRIVATE_KEY": settings.FINIK_PRIVATE_KEY,
        "FINIK_STATUS_API_URL": settings.FINIK_STATUS_API_URL,
    }
    missing = [name for name, value in required_settings.items() if not value]
    if missing:
        raise PaymentGatewayError(f"Не настроены параметры проверки Finik: {', '.join(missing)}.")

    encoded_payment_id = quote(str(payment_id), safe="")
    if "{payment_id}" in settings.FINIK_STATUS_API_URL:
        target_url = settings.FINIK_STATUS_API_URL.format(payment_id=encoded_payment_id)
    else:
        target_url = f"{settings.FINIK_STATUS_API_URL.rstrip('/')}/{encoded_payment_id}"
    parsed_url = urlparse(target_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise PaymentGatewayError("FINIK_STATUS_API_URL должен быть безопасным HTTPS URL.")
    timestamp = current_timestamp_ms()
    signing_headers = {
        "Host": parsed_url.netloc,
        "x-api-key": settings.FINIK_API_KEY,
        "x-api-timestamp": timestamp,
    }
    signature = sign_request(
        "GET",
        parsed_url.path,
        signing_headers,
        None,
        settings.FINIK_PRIVATE_KEY,
        query_params=dict(parse_qsl(parsed_url.query, keep_blank_values=True)),
    )
    try:
        response = requests.get(
            target_url,
            headers={
                "x-api-key": settings.FINIK_API_KEY,
                "x-api-timestamp": timestamp,
                "signature": signature,
            },
            timeout=settings.FINIK_TIMEOUT,
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise PaymentGatewayError("Finik не подтвердил статус HTTP 200.")
        if len(response.content) > settings.FINIK_STATUS_MAX_BODY_BYTES:
            raise PaymentGatewayError("Ответ Finik превышает допустимый размер.")
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.exception("Ошибка проверки статуса платежа %s", payment_id)
        raise PaymentGatewayError("Не удалось проверить статус платежа.") from exc
    if not isinstance(data, dict):
        raise PaymentGatewayError("Finik вернул некорректный формат статуса платежа.")
    return data

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail


@shared_task
def send_sms_code(phone_number, code):
    if settings.FIXED_OTP_CODE:
        return "fixed-otp-no-sms"
    if settings.SMS_PROVIDER == "twilio":
        required_values = (
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_FROM_NUMBER,
        )
        if not all(required_values):
            raise ImproperlyConfigured("Не заполнены обязательные настройки Twilio.")
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"Код подтверждения Элит Маркет: {code}",
            from_=settings.TWILIO_FROM_NUMBER,
            to=phone_number,
        )
        return "sent"

    if settings.SMS_PROVIDER == "console":
        print(f"[Тестовое SMS] {phone_number}: код подтверждения {code}")
        return "stubbed"

    raise ImproperlyConfigured(f"Неизвестный SMS_PROVIDER: {settings.SMS_PROVIDER}.")


@shared_task
def send_admin_verification_email(email, verification_url):
    if not settings.ADMIN_EMAIL_VERIFICATION_ENABLED:
        return "admin-email-disabled"
    send_mail(
        "Подтвердите аккаунт администратора Элит Маркет",
        f"Откройте ссылку для подтверждения аккаунта администратора: {verification_url}",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    return "sent"

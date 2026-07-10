from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_sms_code(phone_number, code):
    if settings.SMS_PROVIDER == "twilio" and settings.TWILIO_ACCOUNT_SID:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"Your Online Shop verification code is {code}",
            from_=settings.TWILIO_FROM_NUMBER,
            to=phone_number,
        )
        return "sent"

    print(f"[SMS stub] {phone_number}: verification code {code}")
    return "stubbed"


@shared_task
def send_admin_verification_email(email, verification_url):
    send_mail(
        "Confirm your Online Shop admin account",
        f"Open this link to confirm your admin account: {verification_url}",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    return "sent"

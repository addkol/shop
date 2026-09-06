from django.conf import settings


def otp_mode(request):
    return {"fixed_otp_enabled": bool(settings.FIXED_OTP_CODE)}

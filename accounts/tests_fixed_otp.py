from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from project.checks import fixed_otp_check, production_configuration_check
from .models import User
from .tasks import send_sms_code
from .views import _send_client_code, VerificationRateLimitError, VerificationDeliveryError


@override_settings(FIXED_OTP_CODE="1234", DEBUG=False, SECURE_SSL_REDIRECT=False)
class FixedOTPTests(TestCase):
    def setUp(self):
        cache.clear()

    def register(self, phone="+996700888001"):
        return self.client.post("/accounts/register/", {"phone_number": phone, "first_name": "Проверка"})

    def test_valid_numbers_use_hashed_challenge_and_login_without_sms(self):
        for phone in ["+996700888001", "+996555888002", "+996999888003"]:
            with self.subTest(phone=phone), patch("accounts.views._dispatch_task") as dispatch:
                self.client.logout()
                response = self.register(phone)
                self.assertEqual(response.status_code, 302)
                user = User.objects.get(phone_number=phone)
                self.assertNotEqual(user.client_profile.verification_code_hash, "1234")
                self.assertTrue(user.client_profile.check_code("1234"))
                self.assertEqual(self.client.post("/accounts/verify/", {"code": "1234"}).status_code, 302)
                self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
                user.client_profile.refresh_from_db()
                self.assertTrue(user.client_profile.phone_verified)
                self.assertEqual(user.client_profile.verification_code_hash, "")
                dispatch.assert_not_called()

    def test_wrong_code_and_attempt_limit(self):
        self.register()
        for _ in range(5):
            self.client.post("/accounts/verify/", {"code": "9999"})
        self.client.post("/accounts/verify/", {"code": "1234"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_expired_code(self):
        self.register()
        profile = User.objects.get(phone_number="+996700888001").client_profile
        profile.verification_code_sent_at = timezone.now() - timezone.timedelta(minutes=10)
        profile.save()
        self.client.post("/accounts/verify/", {"code": "1234"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cannot_verify_without_challenge(self):
        self.client.post("/accounts/verify/", {"code": "1234"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_resend_limit(self):
        self.register()
        with self.assertRaises(VerificationRateLimitError):
            _send_client_code(User.objects.get(phone_number="+996700888001"))

    @override_settings(SMS_IP_MAX_REQUESTS_PER_WINDOW=1)
    def test_ip_rate_limit(self):
        self.register()
        response = self.register("+996700888002")
        self.assertContains(response, "Слишком много запросов")
        self.assertFalse(User.objects.filter(phone_number="+996700888002").exists())

    @override_settings(SMS_PROVIDER="twilio")
    def test_worker_does_not_call_twilio(self):
        with patch("twilio.rest.Client") as provider:
            self.assertEqual(send_sms_code("+996700888001", "1234"), "fixed-otp-no-sms")
            provider.assert_not_called()

    @override_settings(FIXED_OTP_CODE="", CELERY_TASK_ALWAYS_EAGER=True)
    def test_empty_setting_uses_random_and_normal_delivery(self):
        user = User.objects.create_client(phone_number="+996700888001")
        with patch("accounts.models.secrets.randbelow", return_value=6789), patch("accounts.views._dispatch_task") as dispatch:
            _send_client_code(user)
            user.client_profile.refresh_from_db()
            self.assertTrue(user.client_profile.check_code("6789"))
            dispatch.assert_called_once_with(send_sms_code, user.phone_number, "6789")

    def test_fixed_warning(self):
        findings = fixed_otp_check(None)
        self.assertEqual(findings[0].id, "project.W002")
        self.assertEqual(findings[0].level, 30)

    @override_settings(ENVIRONMENT="production", SMS_PROVIDER="console", TWILIO_ACCOUNT_SID="", DEBUG=True)
    def test_only_sms_production_requirements_are_exempt(self):
        ids = {finding.id for finding in production_configuration_check(None)}
        self.assertNotIn("project.E015", ids)
        self.assertNotIn("project.E016", ids)
        self.assertIn("project.E001", ids)

    def test_staff_cannot_use_fixed_otp(self):
        user = User.objects.create_client(phone_number="+996700888001")
        user.is_staff = True
        user.save()
        with self.assertRaises(VerificationDeliveryError):
            _send_client_code(user)

    def test_invalid_phone_is_rejected(self):
        self.assertEqual(self.register("+79990000000").status_code, 200)
        self.assertFalse(User.objects.filter(phone_number="+79990000000").exists())

    def test_registration_does_not_reactivate_blocked_customer(self):
        user = User.objects.create_client(phone_number="+996700888001")
        user.is_active = False
        user.save()
        self.assertEqual(self.register().status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

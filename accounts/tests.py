from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import User
from .security import get_client_ip
from .views import VerificationRateLimitError, _send_client_code


class PhoneAuthSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+996700000000",
            password="secret123",
            is_client=True,
            is_active=True,
        )

    def test_authenticated_user_is_redirected_from_login_page(self):
        self.client.force_login(self.user, backend="accounts.auth_backends.PhoneOrEmailBackend")

        response = self.client.get(reverse("accounts:login"))

        self.assertRedirects(response, reverse("shop:index"), fetch_redirect_response=False)

    def test_verify_code_marks_user_as_remembered_on_device(self):
        profile = self.user.client_profile
        profile.verification_code_hash = make_password("1234")
        profile.verification_code_sent_at = timezone.now()
        profile.verification_attempts = 0
        profile.save(
            update_fields=[
                "verification_code_hash",
                "verification_code_sent_at",
                "verification_attempts",
            ]
        )
        session = self.client.session
        session["verification_phone"] = self.user.phone_number
        session.save()

        response = self.client.post(reverse("accounts:verify"), {"code": "1234"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.session.get("phone_authenticated"))
        self.assertTrue(self.client.session.get_expiry_age() > 0)

    def test_passwordless_backend_authentication_is_rejected(self):
        authenticated_user = authenticate(phone_number=self.user.phone_number, password=None)

        self.assertIsNone(authenticated_user)

    def test_verification_code_is_stored_only_as_hash(self):
        profile = self.user.client_profile

        raw_code = profile.set_new_code()

        profile.refresh_from_db()
        self.assertNotEqual(profile.verification_code_hash, raw_code)
        self.assertTrue(profile.check_code(raw_code))

    def test_verification_code_resend_has_cooldown(self):
        _send_client_code(self.user)

        with self.assertRaises(VerificationRateLimitError):
            _send_client_code(self.user)

    @override_settings(SMS_PROVIDER="unknown")
    def test_sms_configuration_error_is_shown_without_saving_active_code(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"phone_number": self.user.phone_number},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Не удалось отправить код")
        self.user.client_profile.refresh_from_db()
        self.assertEqual(self.user.client_profile.verification_code_hash, "")
        self.assertIsNone(self.user.client_profile.verification_code_sent_at)


class LoginPrivacyAndRateLimitTests(TestCase):
    def tearDown(self):
        cache.clear()

    def test_unknown_phone_uses_same_verification_flow(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"phone_number": "+996700000099"},
            REMOTE_ADDR="198.51.100.20",
        )

        self.assertRedirects(response, reverse("accounts:verify"), fetch_redirect_response=False)
        self.assertTrue(self.client.session["verification_decoy"])

    @override_settings(SMS_IP_MAX_REQUESTS_PER_WINDOW=1, SMS_REQUEST_WINDOW_SECONDS=3600)
    def test_sms_requests_are_limited_by_client_ip(self):
        first = self.client.post(
            reverse("accounts:login"),
            {"phone_number": "+996700000091"},
            REMOTE_ADDR="198.51.100.21",
        )
        second = self.client.post(
            reverse("accounts:login"),
            {"phone_number": "+996700000092"},
            REMOTE_ADDR="198.51.100.21",
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "Слишком много запросов с этого устройства")

    @override_settings(CLIENT_IP_HEADER="HTTP_X_FORWARDED_FOR", CLIENT_IP_TRUSTED_HOPS=2)
    def test_client_ip_uses_configured_trusted_proxy_hops(self):
        request = RequestFactory().get(
            "/",
            HTTP_X_FORWARDED_FOR="198.51.100.30, 10.0.0.10, 10.0.0.11",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(get_client_ip(request), "10.0.0.10")


class AdminLoginSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongAdminPassword123!",
        )

    def tearDown(self):
        cache.clear()

    def test_django_admin_login_uses_rate_limited_view(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/admin_login.html")

    @override_settings(ADMIN_LOGIN_MAX_ATTEMPTS=1, ADMIN_LOGIN_WINDOW_SECONDS=900)
    def test_django_admin_login_is_rate_limited(self):
        credentials = {"username": self.admin.email, "password": "wrong-password"}

        first = self.client.post(reverse("admin:login"), credentials, REMOTE_ADDR="198.51.100.50")
        second = self.client.post(reverse("admin:login"), credentials, REMOTE_ADDR="198.51.100.50")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "Слишком много попыток входа")

    def test_legacy_admin_login_does_not_accept_credentials(self):
        response = self.client.post(
            reverse("accounts:admin-login"),
            {"username": self.admin.email, "password": "StrongAdminPassword123!"},
        )

        self.assertRedirects(response, reverse("admin:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

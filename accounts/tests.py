from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import ClientProfile, User


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
        profile.verification_code = "1234"
        profile.verification_code_sent_at = timezone.now()
        profile.verification_attempts = 0
        profile.save(
            update_fields=[
                "verification_code",
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

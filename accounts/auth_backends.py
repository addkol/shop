from django.contrib.auth.backends import ModelBackend

from .managers import UserManager
from .models import User


class PhoneOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("email") or kwargs.get("phone_number")
        if not identifier:
            return None

        normalized_phone = UserManager.normalize_phone(identifier)
        try:
            if "@" in identifier:
                user = User.objects.get(email__iexact=identifier)
            else:
                user = User.objects.get(phone_number=normalized_phone)
        except User.DoesNotExist:
            return None

        if password is None:
            return user if self.user_can_authenticate(user) else None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

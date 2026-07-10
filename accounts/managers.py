from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def normalize_phone(phone_number):
        if not phone_number:
            return phone_number
        return "".join(ch for ch in phone_number if ch.isdigit() or ch == "+")

    def create_user(self, email=None, phone_number=None, password=None, **extra_fields):
        if not email and not phone_number:
            raise ValueError("Users must have an email or phone number.")
        email = self.normalize_email(email) if email else None
        phone_number = self.normalize_phone(phone_number)
        user = self.model(email=email, phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_client(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_client", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(phone_number=phone_number, password=password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if not email:
            raise ValueError("Superuser must have an email address.")

        return self.create_user(email=email, password=password, **extra_fields)

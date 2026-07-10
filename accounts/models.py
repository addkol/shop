import secrets

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="Номер телефона")
    email = models.EmailField(unique=True, null=True, blank=True, verbose_name="Электронная почта")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Отчество")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Фамилия")
    is_active = models.BooleanField(default=True, verbose_name="Активный")
    is_client = models.BooleanField(default=False, verbose_name="Клиент")
    is_admin = models.BooleanField(default=False, verbose_name="Администратор")
    is_staff = models.BooleanField(default=False, verbose_name="Стафф")
    date_joined = models.DateTimeField(default=timezone.now, verbose_name="Дата регистрации")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.email or self.phone_number or f"user-{self.pk}"

    def get_full_name(self):
        return " ".join(part for part in [self.first_name, self.last_name] if part).strip()

    def get_short_name(self):
        return self.first_name or self.email or self.phone_number or str(self.pk)


class ClientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="client_profile", verbose_name="Пользователь")
    phone_verified = models.BooleanField(default=False, verbose_name="Телефон подтвержден")
    verification_code = models.CharField(max_length=4, blank=True, verbose_name="Код подтверждения")
    verification_code_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Код отправлен")
    verification_attempts = models.PositiveSmallIntegerField(default=0, verbose_name="Попытки подтверждения")

    class Meta:
        verbose_name = "Профиль клиента"
        verbose_name_plural = "Профили клиентов"

    def __str__(self):
        return f"Профиль клиента для {self.user}"

    def set_new_code(self):
        self.verification_code = f"{secrets.randbelow(10000):04d}"
        self.verification_code_sent_at = timezone.now()
        self.verification_attempts = 0
        self.save(
            update_fields=[
                "verification_code",
                "verification_code_sent_at",
                "verification_attempts",
            ]
        )
        return self.verification_code

    def mark_verified(self):
        self.phone_verified = True
        self.verification_code = ""
        self.verification_attempts = 0
        self.save(update_fields=["phone_verified", "verification_code", "verification_attempts"])


class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="admin_profile", verbose_name="Пользователь")
    email_verified = models.BooleanField(default=False, verbose_name="Электронная почта подтверждена")
    email_verification_token = models.CharField(max_length=64, blank=True, verbose_name="Токен подтверждения")

    class Meta:
        verbose_name = "Профиль администратора"
        verbose_name_plural = "Профили администраторов"

    def __str__(self):
        return f"Профиль администратора для {self.user}"

    def set_email_token(self):
        self.email_verification_token = secrets.token_urlsafe(32)
        self.save(update_fields=["email_verification_token"])
        return self.email_verification_token

    def mark_verified(self):
        self.email_verified = True
        self.email_verification_token = ""
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.save(update_fields=["email_verified", "email_verification_token"])

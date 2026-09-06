import re

from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField, UserChangeForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password

from .models import User


PHONE_RE = re.compile(r"^\+996\d{9}$")


def normalize_phone(phone_number):
    return "".join(ch for ch in phone_number if ch.isdigit() or ch == "+")


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css_class} form-control".strip()


class AdminUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "phone_number", "is_client", "is_admin", "is_staff", "is_active")


class AdminUserChangeForm(UserChangeForm):
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = (
            "email",
            "phone_number",
            "password",
            "first_name",
            "last_name",
            "is_active",
            "is_client",
            "is_admin",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


class ClientRegistrationForm(BootstrapFormMixin, forms.Form):
    phone_number = forms.CharField(
        label="Номер телефона",
        help_text="Формат: +996 XXX XXX XXX",
        max_length=20,
    )
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)

    def clean_phone_number(self):
        phone_number = normalize_phone(self.cleaned_data["phone_number"])
        if not PHONE_RE.match(phone_number):
            raise forms.ValidationError("Используйте формат Кыргызстана: +996 XXX XXX XXX.")
        return phone_number


class PhoneLoginForm(BootstrapFormMixin, forms.Form):
    phone_number = forms.CharField(label="Номер телефона", max_length=20)

    def clean_phone_number(self):
        phone_number = normalize_phone(self.cleaned_data["phone_number"])
        if not PHONE_RE.match(phone_number):
            raise forms.ValidationError("Используйте формат Кыргызстана: +996 XXX XXX XXX.")
        return phone_number


class VerificationCodeForm(BootstrapFormMixin, forms.Form):
    code = forms.CharField(label="Код смс", min_length=4, max_length=4)

    def clean_code(self):
        code = self.cleaned_data["code"]
        if not code.isdigit():
            raise forms.ValidationError("Код должен состоять из четырёх цифр.")
        return code


class AdminRegistrationForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(label="Электронная почта")
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Подтвердить пароль", widget=forms.PasswordInput)

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с этой электронной почтой уже существует.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password1") != cleaned_data.get("password2"):
            self.add_error("password2", "Пароли не совпадают.")
        elif cleaned_data.get("password1"):
            validate_password(cleaned_data["password1"])
        return cleaned_data

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
            is_admin=True,
            is_staff=True,
            is_active=False,
        )

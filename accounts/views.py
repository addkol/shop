from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from shop.cart import merge_session_cart_to_db
from shop.forms import CancelOrderForm
from shop.models import Order

from .forms import (
    AdminRegistrationForm,
    ClientRegistrationForm,
    PhoneLoginForm,
    VerificationCodeForm,
)
from .models import AdminProfile, ClientProfile, User
from .tasks import send_admin_verification_email, send_sms_code


def _dispatch_task(task, *args):
    try:
        if settings.CELERY_TASK_ALWAYS_EAGER:
            return task(*args)
        return task.delay(*args)
    except Exception as exc:
        print(f"[task fallback] {task.name}: {exc}")
        return task(*args)


def _send_client_code(user):
    profile, _ = ClientProfile.objects.get_or_create(user=user)
    code = profile.set_new_code()
    print(f"[auth] sending verification code {code} to {user.phone_number} via {settings.SMS_PROVIDER}")
    _dispatch_task(send_sms_code, user.phone_number, code)


def _remember_user_on_device(request, user):
    login(request, user, backend="accounts.auth_backends.PhoneOrEmailBackend")
    request.session["phone_authenticated"] = True
    request.session.set_expiry(60 * 60 * 24 * 30)
    request.session.modified = True


def register_client(request):
    form = ClientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone_number = form.cleaned_data["phone_number"]
        user, created = User.objects.get_or_create(
            phone_number=phone_number,
            defaults={
                "is_client": True,
                "is_active": True,
                "first_name": form.cleaned_data.get("first_name", ""),
                "last_name": form.cleaned_data.get("last_name", ""),
            },
        )
        if not created:
            user.is_client = True
            user.is_active = True
            user.first_name = form.cleaned_data.get("first_name") or user.first_name
            user.last_name = form.cleaned_data.get("last_name") or user.last_name
            user.save(update_fields=["is_client", "is_active", "first_name", "last_name"])

        _send_client_code(user)
        request.session["verification_phone"] = user.phone_number
        messages.success(request, "Мы отправили код подтверждения на ваш телефон.")
        return redirect("accounts:verify")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("shop:index")

    form = PhoneLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone_number = form.cleaned_data["phone_number"]
        try:
            user = User.objects.get(phone_number=phone_number, is_client=True)
        except User.DoesNotExist:
            form.add_error("phone_number", "Клиент с таким номером телефона не найден.")
        else:
            _send_client_code(user)
            request.session["verification_phone"] = user.phone_number
            request.session.set_expiry(60 * 60 * 24 * 30)
            messages.success(request, "Мы отправили код подтверждения на ваш телефон.")
            return redirect("accounts:verify")
    return render(request, "accounts/login.html", {"form": form})


def verify_code(request):
    phone_number = request.session.get("verification_phone")
    if not phone_number:
        messages.error(request, "Сначала введите номер телефона.")
        return redirect("accounts:login")

    user = get_object_or_404(User, phone_number=phone_number, is_client=True)
    profile = get_object_or_404(ClientProfile, user=user)
    form = VerificationCodeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        if profile.verification_attempts >= settings.SMS_MAX_ATTEMPTS:
            messages.error(request, "Слишком много попыток. Запросите новый код.")
            return redirect("accounts:login")

        if profile.verification_code_sent_at:
            expires_at = profile.verification_code_sent_at + timezone.timedelta(
                seconds=settings.SMS_CODE_TTL_SECONDS
            )
            if timezone.now() > expires_at:
                messages.error(request, "Срок действия кода истёк. Запросите новый код.")
                return redirect("accounts:login")

        profile.verification_attempts += 1
        profile.save(update_fields=["verification_attempts"])

        if form.cleaned_data["code"] != profile.verification_code:
            form.add_error("code", "Неверный код подтверждения.")
        else:
            profile.mark_verified()
            _remember_user_on_device(request, user)
            merge_session_cart_to_db(user, request.session)
            request.session.pop("verification_phone", None)
            messages.success(request, "Вы вошли в аккаунт.")
            return redirect("shop:index")

    return render(request, "accounts/verify.html", {"form": form, "phone_number": phone_number})


def register_admin(request):
    form = AdminRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        profile, _ = AdminProfile.objects.get_or_create(user=user)
        token = profile.set_email_token()
        verification_url = request.build_absolute_uri(
            reverse("accounts:verify-admin-email", kwargs={"token": token})
        )
        _dispatch_task(send_admin_verification_email, user.email, verification_url)
        messages.success(request, "Проверьте почту, чтобы активировать аккаунт администратора.")
        return redirect("accounts:admin-login")
    return render(request, "accounts/admin_register.html", {"form": form})


def admin_login(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if not user.is_admin and not user.is_staff:
            form.add_error(None, "Этот вход доступен только администраторам.")
        else:
            login(request, user)
            return redirect("admin:index")
    return render(request, "accounts/admin_login.html", {"form": form})


def verify_admin_email(request, token):
    profile = get_object_or_404(AdminProfile, email_verification_token=token)
    profile.mark_verified()
    messages.success(request, "Почта администратора подтверждена. Теперь можно войти.")
    return redirect("accounts:admin-login")


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Вы вышли из аккаунта.")
    return redirect("shop:index")


@login_required
def profile_view(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items").select_related(
        "shipping_address"
    )
    unpaid_orders = [order for order in orders if order.can_be_paid]
    addresses = request.user.addresses.all()
    return render(
        request,
        "profile.html",
        {
            "orders": orders,
            "unpaid_orders": unpaid_orders,
            "addresses": addresses,
            "cancel_form": CancelOrderForm(),
        },
    )

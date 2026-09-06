import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

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
from .security import consume_rate_limit, get_client_ip, reset_rate_limit
from .tasks import send_admin_verification_email, send_sms_code


logger = logging.getLogger("accounts.auth")


class VerificationRateLimitError(Exception):
    pass


class VerificationDeliveryError(Exception):
    pass


def _dispatch_task(task, *args):
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return task(*args)
    try:
        return task.delay(*args)
    except Exception as exc:
        logger.exception("Фоновая задача %s недоступна, выполняется синхронно: %s", task.name, exc)
        return task(*args)


def _send_client_code(user):
    if settings.FIXED_OTP_CODE and (user.is_staff or user.is_superuser or user.is_admin):
        raise VerificationDeliveryError("Для сотрудников используйте вход администратора с паролем.")
    now = timezone.now()
    with transaction.atomic():
        ClientProfile.objects.get_or_create(user=user)
        profile = ClientProfile.objects.select_for_update().get(user=user)
        window_started_at = profile.verification_requests_started_at
        window_seconds = settings.SMS_REQUEST_WINDOW_SECONDS

        if not window_started_at or (now - window_started_at).total_seconds() >= window_seconds:
            profile.verification_requests_started_at = now
            profile.verification_requests_count = 0
            profile.save(update_fields=["verification_requests_started_at", "verification_requests_count"])

        if profile.verification_code_sent_at:
            elapsed = (now - profile.verification_code_sent_at).total_seconds()
            if elapsed < settings.SMS_RESEND_COOLDOWN_SECONDS:
                wait_seconds = max(1, int(settings.SMS_RESEND_COOLDOWN_SECONDS - elapsed))
                raise VerificationRateLimitError(f"Новый код можно запросить через {wait_seconds} сек.")

        if profile.verification_requests_count >= settings.SMS_MAX_REQUESTS_PER_WINDOW:
            raise VerificationRateLimitError("Слишком много запросов кода. Повторите попытку позже.")

        code = profile.set_new_code(now=now)

    if settings.FIXED_OTP_CODE:
        return

    try:
        _dispatch_task(send_sms_code, user.phone_number, code)
    except Exception as exc:
        ClientProfile.objects.filter(pk=profile.pk).update(
            verification_code_hash="",
            verification_code_sent_at=None,
        )
        logger.exception("Не удалось отправить код подтверждения пользователю %s", user.pk)
        raise VerificationDeliveryError(
            "Не удалось отправить код. Проверьте номер или повторите попытку позже."
        ) from exc


def _remember_user_on_device(request, user):
    login(request, user, backend="accounts.auth_backends.PhoneOrEmailBackend")
    request.session["phone_authenticated"] = True
    request.session.set_expiry(60 * 60 * 24 * 30)
    request.session.modified = True


def _check_sms_ip_rate_limit(request):
    if not consume_rate_limit(
        "sms-request",
        get_client_ip(request),
        settings.SMS_IP_MAX_REQUESTS_PER_WINDOW,
        settings.SMS_REQUEST_WINDOW_SECONDS,
    ):
        raise VerificationRateLimitError("Слишком много запросов с этого устройства. Повторите позже.")


def register_client(request):
    form = ClientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone_number = form.cleaned_data["phone_number"]
        try:
            _check_sms_ip_rate_limit(request)
        except VerificationRateLimitError as exc:
            form.add_error("phone_number", str(exc))
            return render(request, "accounts/register.html", {"form": form})
        user = User.objects.filter(phone_number=phone_number).first()
        if user and (not user.is_client or not user.is_active):
            form.add_error("phone_number", "Этот номер уже используется другим аккаунтом.")
            return render(request, "accounts/register.html", {"form": form})

        if user is None:
            user = User.objects.create_client(
                phone_number=phone_number,
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
            )
        else:
            user.is_client = True
            user.first_name = form.cleaned_data.get("first_name") or user.first_name
            user.last_name = form.cleaned_data.get("last_name") or user.last_name
            update_fields = ["is_client", "first_name", "last_name"]
            if not user.password:
                user.set_unusable_password()
                update_fields.append("password")
            user.save(update_fields=update_fields)

        try:
            _send_client_code(user)
        except (VerificationRateLimitError, VerificationDeliveryError) as exc:
            form.add_error("phone_number", str(exc))
            return render(request, "accounts/register.html", {"form": form})
        request.session["verification_phone"] = user.phone_number
        request.session["verification_decoy"] = False
        messages.success(request, "Введите временный код подтверждения. SMS не отправляется." if settings.FIXED_OTP_CODE else "Мы отправили код подтверждения на ваш телефон.")
        return redirect("accounts:verify")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("shop:index")

    form = PhoneLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone_number = form.cleaned_data["phone_number"]
        try:
            _check_sms_ip_rate_limit(request)
        except VerificationRateLimitError as exc:
            form.add_error("phone_number", str(exc))
            return render(request, "accounts/login.html", {"form": form})

        user = User.objects.filter(phone_number=phone_number, is_client=True, is_active=True).first()
        if user:
            try:
                _send_client_code(user)
            except (VerificationRateLimitError, VerificationDeliveryError) as exc:
                form.add_error("phone_number", str(exc))
                return render(request, "accounts/login.html", {"form": form})
        request.session["verification_phone"] = phone_number
        request.session["verification_decoy"] = user is None
        request.session["verification_decoy_attempts"] = 0
        request.session.set_expiry(60 * 60 * 24 * 30)
        messages.success(request, "Если аккаунт существует, введите временный код. SMS не отправляется." if settings.FIXED_OTP_CODE else "Если аккаунт существует, код подтверждения отправлен на телефон.")
        return redirect("accounts:verify")
    return render(request, "accounts/login.html", {"form": form})


@transaction.atomic
def verify_code(request):
    phone_number = request.session.get("verification_phone")
    if not phone_number:
        messages.error(request, "Сначала введите номер телефона.")
        return redirect("accounts:login")

    is_decoy = request.session.get("verification_decoy", False)
    user = None if is_decoy else get_object_or_404(User, phone_number=phone_number, is_client=True, is_active=True)
    profile = None if is_decoy else get_object_or_404(ClientProfile.objects.select_for_update(), user=user)
    form = VerificationCodeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        if user and settings.FIXED_OTP_CODE and (user.is_staff or user.is_superuser or user.is_admin):
            messages.error(request, "Для сотрудников используйте вход администратора с паролем.")
            return redirect("admin:login")
        if is_decoy:
            attempts = request.session.get("verification_decoy_attempts", 0) + 1
            request.session["verification_decoy_attempts"] = attempts
            if attempts >= settings.SMS_MAX_ATTEMPTS:
                request.session.pop("verification_phone", None)
                request.session.pop("verification_decoy", None)
                request.session.pop("verification_decoy_attempts", None)
                messages.error(request, "Слишком много попыток. Запросите новый код.")
                return redirect("accounts:login")
            form.add_error("code", "Неверный код подтверждения.")
            return render(request, "accounts/verify.html", {"form": form, "phone_number": phone_number})

        if profile.verification_attempts >= settings.SMS_MAX_ATTEMPTS:
            messages.error(request, "Слишком много попыток. Запросите новый код.")
            return redirect("accounts:login")

        if not profile.verification_code_sent_at or not profile.verification_code_hash:
            messages.error(request, "Запросите новый код подтверждения.")
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

        if not profile.check_code(form.cleaned_data["code"]):
            form.add_error("code", "Неверный код подтверждения.")
        else:
            profile.mark_verified()
            _remember_user_on_device(request, user)
            merge_session_cart_to_db(user, request.session)
            request.session.pop("verification_phone", None)
            request.session.pop("verification_decoy", None)
            request.session.pop("verification_decoy_attempts", None)
            messages.success(request, "Вы вошли в аккаунт.")
            return redirect("shop:index")

    return render(request, "accounts/verify.html", {"form": form, "phone_number": phone_number})


@login_required(login_url="admin:login")
@user_passes_test(lambda user: user.is_superuser, login_url="admin:login")
def register_admin(request):
    if not settings.ADMIN_EMAIL_VERIFICATION_ENABLED:
        return HttpResponse("Регистрация администраторов по email временно отключена.", status=503)
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
        return redirect("admin:login")
    return render(request, "accounts/admin_register.html", {"form": form})


@sensitive_post_parameters("password")
@never_cache
def admin_login(request):
    ip_address = get_client_ip(request)
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        allowed = consume_rate_limit(
            "admin-login",
            ip_address,
            settings.ADMIN_LOGIN_MAX_ATTEMPTS,
            settings.ADMIN_LOGIN_WINDOW_SECONDS,
        )
        if not allowed:
            form.add_error(None, "Слишком много попыток входа. Повторите позже.")
        elif form.is_valid():
            user = form.get_user()
            if not user.is_admin and not user.is_staff:
                form.add_error(None, "Этот вход доступен только администраторам.")
            else:
                reset_rate_limit("admin-login", ip_address)
                login(request, user)
                destination = request.POST.get("next") or request.GET.get("next")
                if destination and url_has_allowed_host_and_scheme(
                    destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()
                ):
                    return redirect(destination)
                return redirect("dashboard:home")
    return render(request, "accounts/admin_login.html", {"form": form})


def verify_admin_email(request, token):
    if not settings.ADMIN_EMAIL_VERIFICATION_ENABLED:
        return HttpResponse("Подтверждение администраторов по email временно отключено.", status=503)
    profile = get_object_or_404(AdminProfile, email_verification_token=AdminProfile.token_digest(token))
    if not profile.email_verification_sent_at:
        messages.error(request, "Ссылка подтверждения недействительна.")
        return redirect("admin:login")
    expires_at = profile.email_verification_sent_at + timezone.timedelta(
        seconds=settings.ADMIN_EMAIL_VERIFICATION_TTL_SECONDS
    )
    if timezone.now() > expires_at:
        messages.error(request, "Срок действия ссылки подтверждения истёк.")
        return redirect("admin:login")
    profile.mark_verified()
    messages.success(request, "Почта администратора подтверждена. Теперь можно войти.")
    return redirect("admin:login")


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
    addresses = request.user.addresses.filter(is_saved=True)
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

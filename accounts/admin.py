from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .forms import AdminUserCreationForm, AdminUserChangeForm
from .models import AdminProfile, ClientProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    model = User
    list_display = (
        "email",
        "phone_number",
        "first_name",
        "last_name",
        "is_client",
        "is_admin",
        "is_staff",
        "is_active",
    )
    list_filter = ("is_client", "is_admin", "is_staff", "is_active")
    ordering = ("email", "phone_number")
    search_fields = ("email", "phone_number", "first_name", "last_name")
    fieldsets = (
        ("Основная информация", {"fields": ("email", "phone_number", "password")}),
        ("Личные данные", {"fields": ("first_name", "last_name")}),
        (
            "Права акцесса",
            {
                "fields": (
                    "is_active",
                    "is_client",
                    "is_admin",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Важные даты", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "phone_number",
                    "password1",
                    "password2",
                    "is_client",
                    "is_admin",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_verified", "verification_code_sent_at", "verification_attempts")
    search_fields = ("user__phone_number", "user__first_name", "user__last_name")


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "email_verified")
    search_fields = ("user__email",)

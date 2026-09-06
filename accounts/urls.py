from django.urls import path
from django.views.generic import RedirectView

from . import views


app_name = "accounts"

urlpatterns = [
    path("register/", views.register_client, name="register"),
    path("login/", views.login_view, name="login"),
    path("verify/", views.verify_code, name="verify"),
    path("admin/register/", views.register_admin, name="admin-register"),
    path(
        "admin/login/",
        RedirectView.as_view(pattern_name="admin:login", permanent=False),
        name="admin-login",
    ),
    path("admin/verify/<str:token>/", views.verify_admin_email, name="verify-admin-email"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
]

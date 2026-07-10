from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path("register/", views.register_client, name="register"),
    path("login/", views.login_view, name="login"),
    path("verify/", views.verify_code, name="verify"),
    path("admin/register/", views.register_admin, name="admin-register"),
    path("admin/login/", views.admin_login, name="admin-login"),
    path("admin/verify/<str:token>/", views.verify_admin_email, name="verify-admin-email"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
]

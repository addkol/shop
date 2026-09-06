from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from accounts.views import admin_login

from .media_views import serve_media
from .views import health_check, liveness_check


urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url="/static/img/favicon.svg", permanent=True)),
    path("health/", health_check, name="health-check"),
    path("health/live/", liveness_check, name="liveness-check"),
    path("admin/login/", admin_login, name="secure-admin-login"),
    path("admin/", admin.site.urls),
    path("dashboard/", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("", include("payment.urls")),
    path("", include("shop.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA_FILES and not settings.USE_S3:
    media_prefix = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [re_path(rf"^{media_prefix}(?P<path>.*)$", serve_media)]

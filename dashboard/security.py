from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.views.decorators.cache import never_cache


def staff_permission(*permissions):
    def decorator(view):
        @never_cache
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), reverse("admin:login"))
            if not request.user.is_active or not request.user.is_staff:
                raise PermissionDenied
            if not request.user.has_perms(permissions):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

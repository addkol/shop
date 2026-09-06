import secrets

from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(18)
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        response.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        if request.path.startswith("/admin/"):
            csp = (
                "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
                "form-action 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; font-src 'self' data:; connect-src 'self'"
            )
        else:
            csp = settings.CONTENT_SECURITY_POLICY.format(nonce=request.csp_nonce)
        response.setdefault("Content-Security-Policy", csp)
        if request.path.startswith(("/accounts/", "/admin/", "/checkout/", "/profile/", "/orders/", "/pay/")):
            response.setdefault("Cache-Control", "no-store")
        return response

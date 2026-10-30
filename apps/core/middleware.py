from django.http import HttpResponsePermanentRedirect


class LegacyPathMiddleware:
    """Herstelt links van de oude site die een backslash voor het pad hadden (/%5Cpagina/170)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/\\"):
            clean = "/" + path.lstrip("/\\")
            query = request.META.get("QUERY_STRING")
            return HttpResponsePermanentRedirect(clean + (f"?{query}" if query else ""))
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Strikte Content-Security-Policy voor de publieke site (niet voor de Wagtail-beheeromgeving)."""

    PUBLIC_CSP = "; ".join(
        [
            "default-src 'self'",
            "img-src 'self' data:",
            "style-src 'self' 'unsafe-inline'",
            "script-src 'self'",
            "frame-src https://www.youtube-nocookie.com",
            "form-action 'self'",
            "base-uri 'self'",
            "frame-ancestors 'self'",
        ]
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(("/admin/", "/accounts/")):
            response.setdefault("Content-Security-Policy", self.PUBLIC_CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

"""Aanmelden op de beheeromgeving via Microsoft 365 (Entra ID, OpenID Connect)."""

import logging

import msal
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from apps.core.models import Integraties, Toegang

from .roles import apply_role

logger = logging.getLogger(__name__)
FLOW_KEY = "sso_flow"
NEXT_KEY = "sso_next"


def _safe_next(request, value):
    if value and url_has_allowed_host_and_scheme(value, {request.get_host()}, require_https=request.is_secure()):
        return value
    return "/admin/"


def _msal_app(integraties):
    return msal.ConfidentialClientApplication(
        integraties.client_id,
        authority=f"https://login.microsoftonline.com/{integraties.tenant_id}",
        client_credential=settings.AZURE_CLIENT_SECRET,
    )


def _sso_ready(integraties):
    return bool(integraties.tenant_id and integraties.client_id and settings.AZURE_CLIENT_SECRET)


@never_cache
def login_view(request):
    next_url = _safe_next(request, request.GET.get("next"))
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(next_url)
    integraties = Integraties.load(request_or_site=request)
    ready = _sso_ready(integraties)
    if ready and request.GET.get("start"):
        flow = _msal_app(integraties).initiate_auth_code_flow(
            scopes=[], redirect_uri=request.build_absolute_uri("/admin/login/callback/")
        )
        request.session[FLOW_KEY] = flow
        request.session[NEXT_KEY] = next_url
        return redirect(flow["auth_uri"])
    return render(
        request,
        "accounts/login.html",
        {"sso_ready": ready, "next": next_url, "password_login": settings.ALLOW_PASSWORD_LOGIN},
    )


@never_cache
def callback_view(request):
    integraties = Integraties.load(request_or_site=request)
    flow = request.session.pop(FLOW_KEY, None)
    if not flow or not _sso_ready(integraties):
        return redirect("accounts:login")
    try:
        result = _msal_app(integraties).acquire_token_by_auth_code_flow(flow, request.GET.dict())
    except ValueError:
        logger.warning("Ongeldige SSO-terugkeer (state komt niet overeen)")
        return redirect("accounts:login")
    claims = result.get("id_token_claims")
    if not claims:
        logger.warning("SSO mislukt: %s", result.get("error_description", result.get("error")))
        return render(request, "accounts/denied.html", {"reason": "De aanmelding bij Microsoft is mislukt."}, status=403)
    if claims.get("tid") != integraties.tenant_id:
        return render(request, "accounts/denied.html", {"reason": "Dit account hoort niet bij de club."}, status=403)

    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    role = Toegang.load(request_or_site=request).role_for(email)
    User = get_user_model()
    user = User.objects.filter(username=email).first()
    if role is None:
        if user:
            apply_role(user, None)
        return render(
            request,
            "accounts/denied.html",
            {"reason": f"{email} heeft geen toegang tot de beheeromgeving.", "email": email},
            status=403,
        )

    if user is None:
        user = User(username=email)
        user.set_unusable_password()
    user.email = email
    user.first_name = claims.get("given_name", "")[:150]
    user.last_name = claims.get("family_name", "")[:150]
    if not user.first_name and claims.get("name"):
        user.first_name = claims["name"][:150]
    apply_role(user, role)
    next_url = request.session.pop(NEXT_KEY, "/admin/")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(_safe_next(request, next_url))


class PasswordLogin(LoginView):
    template_name = "accounts/password_login.html"


def password_login_view(request):
    """Noodtoegang, enkel actief met ALLOW_PASSWORD_LOGIN=1 in Portainer."""
    if not settings.ALLOW_PASSWORD_LOGIN:
        raise Http404
    return PasswordLogin.as_view()(request)

"""Auth endpoints: register/login/refresh/logout/me.

HTTP status codes: 200 OK · 201 registered · 400 duplicate username/email ·
401 bad credentials / missing-expired-revoked refresh token ·
403 CSRF mismatch (refresh only) · 429 rate limited.
"""
import logging
import secrets
from typing import cast

from django.conf import settings
from django.contrib.auth import authenticate
from django.http import JsonResponse
from ninja import Router
from ninja.errors import HttpError
from ninja.throttling import BaseThrottle

from config.throttling import AuthAnonThrottle, SessionAuthThrottle

from . import services as auth_services
from .auth import AuthBearer
from .models import User
from .schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = Router(auth=None)

logger = logging.getLogger("accounts")


def _client_ip(request) -> str:
    """Best-effort client IP for audit logs (respects X-Forwarded-For)."""
    return request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))

AUTH_THROTTLE: list[BaseThrottle] = [AuthAnonThrottle("5/m")]


def _set_auth_cookies(response, refresh_token: str) -> None:
    auth_services.set_refresh_cookie(response, refresh_token)
    auth_services.set_csrf_cookie(response)


def _auth_failure_response(status: int, detail: str) -> JsonResponse:
    response = JsonResponse({"detail": detail}, status=status)
    auth_services.clear_app_cookies(response)
    return response


@router.post("/register", response={201: TokenOut}, throttle=AUTH_THROTTLE, url_name="register")
def register(request, payload: RegisterIn):
    email = payload.email.lower()
    if User.objects.filter(username=payload.username).exists():
        raise HttpError(400, "That username is already taken.")
    if User.objects.filter(email=email).exists():
        raise HttpError(400, "That email is already registered.")
    user = User.objects.create_user(
        username=payload.username, email=email, password=payload.password
    )
    logger.info("user registered: id=%s username=%s ip=%s", user.pk, user.username, _client_ip(request))
    access, refresh = auth_services.issue_token_pair(user)
    response = JsonResponse(auth_services.token_response(user, access), status=201)
    _set_auth_cookies(response, refresh)
    return response


@router.post("/login", response=TokenOut, throttle=AUTH_THROTTLE, url_name="login")
def login(request, payload: LoginIn):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None:
        logger.warning("login failed: username=%s ip=%s", payload.username, _client_ip(request))
        raise HttpError(401, "Invalid username or password.")
    user = cast(User, user)  # django-stubs: authenticate() -> AbstractBaseUser | None
    logger.info("login ok: user=%s ip=%s", user.username, _client_ip(request))
    access, refresh = auth_services.issue_token_pair(user)
    response = JsonResponse(auth_services.token_response(user, access))
    _set_auth_cookies(response, refresh)
    return response


@router.post("/refresh", response=TokenOut, throttle=AUTH_THROTTLE, url_name="refresh")
def refresh(request):
    token = request.COOKIES.get(settings.COOKIE_REFRESH_NAME)
    if not token:
        raise HttpError(401, "Missing refresh token.")

    header_csrf = request.headers.get("x-csrf-token", "")
    cookie_csrf = request.COOKIES.get(settings.COOKIE_CSRF_NAME, "")
    if not cookie_csrf or not secrets.compare_digest(header_csrf, cookie_csrf):
        return _auth_failure_response(403, "CSRF validation failed.")

    payload = auth_services.safe_decode_token(token, "refresh")
    if payload is None:
        return _auth_failure_response(401, "Refresh token is invalid.")

    if auth_services.is_refresh_revoked(token):
        logger.warning("refresh blocked: revoked token user_id=%s", payload.get("sub"))
        return _auth_failure_response(401, "Refresh token has been revoked.")

    user = auth_services.user_from_payload(payload)
    if user is None:
        return _auth_failure_response(401, "Account no longer exists or is disabled.")

    # Rotation: burn the presented token before issuing a new pair.
    auth_services.revoke_refresh_token(token)
    logger.info("refresh ok: user=%s (rotated)", user.username)
    access, new_refresh = auth_services.issue_token_pair(user)
    response = JsonResponse(auth_services.token_response(user, access))
    _set_auth_cookies(response, new_refresh)
    return response


@router.post("/logout", auth=AuthBearer(), throttle=[SessionAuthThrottle("30/m")], url_name="logout")
def logout(request):
    logger.info("logout: user=%s ip=%s", request.auth.username, _client_ip(request))
    token = request.COOKIES.get(settings.COOKIE_REFRESH_NAME)
    if token:
        auth_services.revoke_refresh_token(token)
    auth_services.prune_blacklist()
    response = JsonResponse({"detail": "Logged out."})
    auth_services.clear_app_cookies(response)
    return response


@router.get("/me", auth=AuthBearer(), response=UserOut, throttle=[SessionAuthThrottle("60/m")], url_name="me")
def me(request):
    return UserOut(**auth_services.user_dict(request.auth))

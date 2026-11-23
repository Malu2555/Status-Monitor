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
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from ninja.throttling import BaseThrottle

from audit.services import audit_log
from config.throttling import (
    AuthAnonThrottle,
    LoginAnonThrottle,
    RefreshAnonThrottle,
    SessionAuthThrottle,
)

from . import abuse
from . import services as auth_services
from .auth import AuthBearer
from .models import User
from .schemas import (
    ApiTokenCreatedOut,
    ApiTokenIn,
    ApiTokenOut,
    ChangeEmailIn,
    ChangePasswordIn,
    DeleteAccountIn,
    LoginIn,
    MessageOut,
    ModerationIn,
    ModerationOut,
    OtpActivatedOut,
    OtpCodeIn,
    OtpEnrollOut,
    RecoveryCodesSummaryOut,
    RegisterIn,
    RequestResetIn,
    ResetConfirmIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)

router = Router(auth=None)

logger = logging.getLogger("accounts")


def _client_ip(request) -> str:
    """Best-effort client IP for audit logs (trusted X-Forwarded-For only)."""
    return abuse.client_ip(request)


def _audit_ip(request) -> dict:
    """Raw proxy headers for the debug_proxy command (truncated, non-secret)."""
    return {
        "remote": request.META.get("REMOTE_ADDR", "")[:64],
        "xff": request.META.get("HTTP_X_FORWARDED_FOR", "")[:300],
    }


AUTH_THROTTLE: list[BaseThrottle] = [AuthAnonThrottle("5/m")]
LOGIN_THROTTLE: list[BaseThrottle] = [LoginAnonThrottle("10/m")]
REFRESH_THROTTLE: list[BaseThrottle] = [RefreshAnonThrottle("60/m")]


def _set_auth_cookies(response, refresh_token: str) -> None:
    auth_services.set_refresh_cookie(response, refresh_token)
    auth_services.set_csrf_cookie(response)


def _auth_failure_response(status: int, detail: str) -> JsonResponse:
    response = JsonResponse({"detail": detail}, status=status)
    auth_services.clear_app_cookies(response)
    return response


@router.post("/register", response={201: TokenOut}, throttle=AUTH_THROTTLE, url_name="register")
def register(request, payload: RegisterIn):
    ip = _client_ip(request)
    if payload.company.strip():
        # Honeypot tripped — almost certainly a bot.
        abuse.note_failure(ip, "honeypot")
        audit_log(request, "abuse.honeypot_hit", user=None, field="company")
        raise HttpError(400, "Registration rejected.")
    if not (payload.accepted_tos and payload.accepted_age):
        raise HttpError(
            400,
            "You must accept the Terms of Service and Privacy Policy and confirm that you are at least 16 years old.",
        )
    email = payload.email.lower()
    if User.objects.filter(username=payload.username).exists():
        raise HttpError(400, "That username is already taken.")
    if User.objects.filter(email=email).exists():
        raise HttpError(400, "That email is already registered.")
    user = User.objects.create_user(username=payload.username, email=email, password=payload.password)
    auth_services.record_tos_acceptance(user)
    logger.info("user registered: id=%s username=%s ip=%s", user.pk, user.username, _client_ip(request))
    audit_log(
        request,
        "auth.register",
        user=user,
        username=user.username,
        user_id=user.pk,
        tos_version=user.tos_version,
        age_confirmed=True,
        **_audit_ip(request),
    )
    try:
        auth_services.send_verification_email(user)
    except Exception:
        logger.exception("verification email failed: user=%s", user.pk)
    access, refresh = auth_services.issue_token_pair(user)
    response = JsonResponse(auth_services.token_response(user, access), status=201)
    _set_auth_cookies(response, refresh)
    return response


@router.post("/login", response=TokenOut, throttle=LOGIN_THROTTLE, url_name="login")
def login(request, payload: LoginIn):
    if abuse.login_locked(payload.username):
        logger.warning("login locked: username=%s ip=%s", payload.username, _client_ip(request))
        audit_log(request, "auth.login_locked", user=None, username=payload.username)
        raise HttpError(429, "Too many failed attempts. Try again later.")
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None:
        logger.warning("login failed: username=%s ip=%s", payload.username, _client_ip(request))
        abuse.note_failure(_client_ip(request), "login")
        if abuse.note_login_failure(payload.username):
            audit_log(request, "auth.login_username_locked", username=payload.username)
        audit_log(request, "auth.login_failed", user=None, username=payload.username, **_audit_ip(request))
        raise HttpError(401, "Invalid username or password.")
    user = cast(User, user)  # django-stubs: authenticate() -> AbstractBaseUser | None
    if auth_services.user_otp_enabled(user) and not auth_services.verify_otp_or_recovery(user, payload.otp or ""):
        logger.warning("login otp refused: user=%s ip=%s", user.username, _client_ip(request))
        abuse.note_failure(_client_ip(request), "otp")
        abuse.note_login_failure(payload.username)
        audit_log(request, "auth.login_otp_failed", user=user, username=user.username)
        raise HttpError(401, "Invalid two-factor code.")
    abuse.clear_login_failures(payload.username)
    logger.info("login ok: user=%s ip=%s", user.username, _client_ip(request))
    audit_log(request, "auth.login", user=user, username=user.username, **_audit_ip(request))
    access, refresh = auth_services.issue_token_pair(user)
    response = JsonResponse(auth_services.token_response(user, access))
    _set_auth_cookies(response, refresh)
    return response


@router.post("/refresh", response=TokenOut, throttle=REFRESH_THROTTLE, url_name="refresh")
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
    audit_log(request, "auth.logout", user=request.auth)
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


# --------------------------------------------------------------------------
# Self-service account management
# --------------------------------------------------------------------------
@router.post(
    "/change-password",
    auth=AuthBearer(),
    response=TokenOut,
    throttle=[SessionAuthThrottle("5/m")],
    url_name="change_password",
)
def change_password(request, payload: ChangePasswordIn):
    if not auth_services.change_password(request.auth, payload.current_password, payload.new_password):
        abuse.note_failure(_client_ip(request), "password_change")
        raise HttpError(400, "Current password is incorrect.")
    logger.info("password changed: user=%s", request.auth.username)
    audit_log(request, "auth.password_changed", user=request.auth)
    # Every old token is now invalid; hand this session a fresh pair.
    access, refresh = auth_services.issue_token_pair(request.auth)
    response = JsonResponse(auth_services.token_response(request.auth, access))
    _set_auth_cookies(response, refresh)
    return response


@router.post(
    "/change-email",
    auth=AuthBearer(),
    response=MessageOut,
    throttle=[SessionAuthThrottle("5/m")],
    url_name="change_email",
)
def change_email(request, payload: ChangeEmailIn):
    user = cast(User, request.auth)
    if not user.check_password(payload.current_password):
        raise HttpError(400, "Current password is incorrect.")
    if payload.new_email == user.email:
        raise HttpError(400, "That is already your email address.")
    if User.objects.filter(email=payload.new_email).exclude(pk=user.pk).exists():
        raise HttpError(400, "That email is already registered.")
    try:
        auth_services.request_email_change(user, payload.new_email)
    except Exception:
        logger.exception("email-change message failed: user=%s", user.pk)
        raise HttpError(503, "Could not send the confirmation email.") from None
    logger.info("email change requested: user=%s", user.username)
    audit_log(request, "auth.email_change_requested", user=user, new_email=payload.new_email)
    return {"detail": "Confirmation link sent to the new address."}


@router.post(
    "/sessions/revoke-others",
    auth=AuthBearer(),
    response=TokenOut,
    throttle=[SessionAuthThrottle("10/m")],
    url_name="revoke_other_sessions",
)
def revoke_other_sessions(request):
    auth_services.invalidate_sessions(request.auth)
    logger.info("all other sessions revoked: user=%s", request.auth.username)
    audit_log(request, "auth.sessions_revoked", user=request.auth)
    access, refresh = auth_services.issue_token_pair(request.auth)
    response = JsonResponse(auth_services.token_response(request.auth, access))
    _set_auth_cookies(response, refresh)
    return response


@router.delete(
    "/me",
    auth=AuthBearer(),
    response={204: None},
    throttle=[SessionAuthThrottle("3/h")],
    url_name="delete_me",
)
def delete_me(request, payload: DeleteAccountIn):
    """Self-service account deletion: anonymise PII, disable, pause monitors."""
    if not request.auth.check_password(payload.current_password):
        raise HttpError(400, "Current password is incorrect.")
    username = request.auth.username
    paused = auth_services.soft_delete_account(request.auth)
    logger.warning("account self-deleted: user=%s paused_monitors=%s", username, paused)
    audit_log(request, "auth.account_self_deleted", user=request.auth, monitors_paused=paused)
    response = HttpResponse(status=204)
    auth_services.clear_app_cookies(response)
    return response


# --------------------------------------------------------------------------
# Account lifecycle: email verification, password reset, opt-in 2FA
# --------------------------------------------------------------------------
@router.post("/verify-email", response=MessageOut, throttle=AUTH_THROTTLE, url_name="verify_email")
def verify_email(request, payload: VerifyEmailIn):
    record = auth_services.consume_account_token_record(payload.token, "verify_email")
    changed = False
    if record is None:
        # A pending email change is confirmed through the same link.
        record = auth_services.consume_account_token_record(payload.token, "email_change")
        if record is None:
            raise HttpError(400, "Invalid or expired verification link.")
        changed = True

    user = record.user
    if changed:
        new_email = (record.payload or {}).get("new_email", "")
        if new_email:
            user.email = new_email
        audit_kind = "auth.email_changed"
        logger.info("email changed: user=%s", user.username)
    else:
        audit_kind = "auth.email_verified"
        logger.info("email verified: user=%s", user.username)

    user.email_verified = True
    user.save(update_fields=["email", "email_verified"])
    audit_log(request, audit_kind, user=user)
    return {"detail": "Email verified."}


@router.post(
    "/resend-verification",
    auth=AuthBearer(),
    response=MessageOut,
    throttle=[SessionAuthThrottle("5/m")],
    url_name="resend_verification",
)
def resend_verification(request):
    if request.auth.email_verified:
        return {"detail": "Email already verified."}
    auth_services.send_verification_email(request.auth)
    logger.info("verification re-sent: user=%s", request.auth.username)
    return {"detail": "Verification email sent."}


@router.post("/request-reset", response=MessageOut, throttle=AUTH_THROTTLE, url_name="request_reset")
def request_reset(request, payload: RequestResetIn):
    # Identical response for known/unknown emails — no user enumeration.
    user = User.objects.filter(email=payload.email.lower()).first()
    if user is not None:
        auth_services.send_password_reset_email(user)
        logger.info("password reset requested: user=%s ip=%s", user.username, _client_ip(request))
    else:
        logger.info("password reset requested for unknown email: ip=%s", _client_ip(request))
    return {"detail": "If that address is registered, a reset link has been sent."}


@router.post("/reset-confirm", response=MessageOut, throttle=AUTH_THROTTLE, url_name="reset_confirm")
def reset_confirm(request, payload: ResetConfirmIn):
    user = auth_services.consume_account_token(payload.token, "password_reset")
    if user is None:
        raise HttpError(400, "Invalid or expired reset link.")
    user.set_password(payload.new_password)
    user.save(update_fields=["password"])
    logger.info("password reset completed: user=%s", user.username)
    audit_log(request, "auth.password_reset", user=user)
    return {"detail": "Password updated — please log in again."}


@router.get("/otp/status", auth=AuthBearer(), throttle=[SessionAuthThrottle("60/m")], url_name="otp_status")
def otp_status(request):
    return {"enabled": auth_services.user_otp_enabled(request.auth)}


@router.post(
    "/otp/enroll",
    auth=AuthBearer(),
    response=OtpEnrollOut,
    throttle=[SessionAuthThrottle("10/m")],
    url_name="otp_enroll",
)
def otp_enroll(request):
    device = auth_services.create_totp_device(request.auth)
    if not device.confirmed:
        logger.info("otp enroll started: user=%s", request.auth.username)
    return {"provisioning_uri": device.config_url}


@router.post(
    "/otp/activate",
    auth=AuthBearer(),
    response=OtpActivatedOut,
    throttle=[SessionAuthThrottle("10/m")],
    url_name="otp_activate",
)
def otp_activate(request, payload: OtpCodeIn):
    if not auth_services.confirm_totp_device(request.auth, payload.code):
        logger.warning("otp activation failed: user=%s", request.auth.username)
        raise HttpError(400, "Invalid code.")
    recovery_codes = auth_services.issue_recovery_codes(request.auth)
    logger.info("otp activated: user=%s", request.auth.username)
    audit_log(
        request,
        "auth.otp_activated",
        user=request.auth,
        recovery_codes=len(recovery_codes),
    )
    return {
        "detail": "Two-factor authentication enabled.",
        "recovery_codes": recovery_codes,
    }


@router.post(
    "/otp/disable",
    auth=AuthBearer(),
    response=MessageOut,
    throttle=[SessionAuthThrottle("10/m")],
    url_name="otp_disable",
)
def otp_disable(request, payload: OtpCodeIn):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from .models import RecoveryCode

    if not auth_services.verify_otp_code(request.auth, payload.code):
        raise HttpError(400, "Invalid code.")
    TOTPDevice.objects.filter(user=request.auth).delete()
    RecoveryCode.objects.filter(user=request.auth).delete()
    logger.info("otp disabled: user=%s", request.auth.username)
    audit_log(request, "auth.otp_disabled", user=request.auth)
    return {"detail": "Two-factor authentication disabled."}


@router.get(
    "/otp/recovery-codes",
    auth=AuthBearer(),
    response=RecoveryCodesSummaryOut,
    throttle=[SessionAuthThrottle("60/m")],
    url_name="otp_recovery_codes",
)
def otp_recovery_codes(request):
    return auth_services.recovery_codes_summary(request.auth)


@router.post(
    "/otp/recovery-codes/regenerate",
    auth=AuthBearer(),
    response=OtpActivatedOut,
    throttle=[SessionAuthThrottle("10/m")],
    url_name="otp_recovery_codes_regenerate",
)
def otp_recovery_codes_regenerate(request, payload: OtpCodeIn):
    if not auth_services.verify_otp_code(request.auth, payload.code):
        raise HttpError(400, "Invalid code.")
    recovery_codes = auth_services.issue_recovery_codes(request.auth)
    logger.info("recovery codes regenerated: user=%s", request.auth.username)
    audit_log(
        request,
        "auth.recovery_codes_regenerated",
        user=request.auth,
        count=len(recovery_codes),
    )
    return {
        "detail": "Recovery codes regenerated.",
        "recovery_codes": recovery_codes,
    }


# --------------------------------------------------------------------------
# Moderation (staff only) — is_active=False cuts off JWT *and* API keys
# --------------------------------------------------------------------------
def _moderation_target(request, user_id: int):
    if not auth_services.is_staff(request.auth):
        raise HttpError(403, "Staff access required.")
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        raise HttpError(404, "User not found.") from None


@router.post(
    "/moderation/users/{user_id}/disable",
    auth=AuthBearer(),
    response=ModerationOut,
    throttle=[SessionAuthThrottle("30/m")],
    url_name="moderation_disable_user",
)
def moderation_disable_user(request, user_id: int, payload: ModerationIn):
    target = _moderation_target(request, user_id)
    if target.pk == request.auth.pk:
        raise HttpError(400, "You cannot disable your own account.")
    paused = auth_services.disable_user(target, payload.reason)
    logger.warning(
        "account disabled: user=%s reason=%s by=%s paused_monitors=%s",
        target.username,
        payload.reason,
        request.auth.username,
        paused,
    )
    audit_log(
        request,
        "moderation.user_disabled",
        user=target,
        reason=payload.reason,
        by=request.auth.username,
        monitors_paused=paused,
    )
    return {
        "id": target.pk,
        "username": target.username,
        "is_active": target.is_active,
        "disabled_reason": target.disabled_reason,
        "disabled_at": target.disabled_at,
        "monitors_paused": paused,
    }


@router.post(
    "/moderation/users/{user_id}/enable",
    auth=AuthBearer(),
    response=ModerationOut,
    throttle=[SessionAuthThrottle("30/m")],
    url_name="moderation_enable_user",
)
def moderation_enable_user(request, user_id: int):
    target = _moderation_target(request, user_id)
    resumed = auth_services.enable_user(target)
    logger.info(
        "account re-enabled: user=%s by=%s resumed_monitors=%s",
        target.username,
        request.auth.username,
        resumed,
    )
    audit_log(
        request,
        "moderation.user_enabled",
        user=target,
        by=request.auth.username,
        monitors_resumed=resumed,
    )
    return {
        "id": target.pk,
        "username": target.username,
        "is_active": target.is_active,
        "disabled_reason": target.disabled_reason,
        "disabled_at": target.disabled_at,
        "monitors_paused": resumed,
    }


# --------------------------------------------------------------------------
# API tokens (programmatic access — send the key as X-API-Key)
# --------------------------------------------------------------------------
@router.get(
    "/tokens",
    auth=AuthBearer(),
    response=list[ApiTokenOut],
    throttle=[SessionAuthThrottle("60/m")],
    url_name="api_tokens",
)
def list_api_tokens(request):
    from .models import ApiToken

    return [
        ApiTokenOut(
            id=token.pk,
            name=token.name,
            prefix=token.prefix,
            scope=token.scope,
            created_at=token.created_at,
            last_used_at=token.last_used_at,
            revoked=token.revoked_at is not None,
        )
        for token in ApiToken.objects.filter(user=request.auth)
    ]


@router.post(
    "/tokens",
    auth=AuthBearer(),
    response=ApiTokenCreatedOut,
    throttle=[SessionAuthThrottle("10/m")],
    url_name="api_token_create",
)
def create_api_token(request, payload: ApiTokenIn):
    raw, record = auth_services.issue_api_token(request.auth, payload.name, payload.scope)
    logger.info(
        "api token created: user=%s id=%s scope=%s",
        request.auth.username,
        record.pk,
        record.scope,
    )
    audit_log(request, "auth.api_token_created", user=request.auth, token_id=record.pk, scope=record.scope)
    return ApiTokenCreatedOut(id=record.pk, name=record.name, token=raw, scope=record.scope)


@router.delete(
    "/tokens/{token_id}",
    auth=AuthBearer(),
    response=MessageOut,
    throttle=[SessionAuthThrottle("10/m")],
    url_name="api_token_revoke",
)
def revoke_api_token(request, token_id: int):
    from .models import ApiToken

    updated = ApiToken.objects.filter(pk=token_id, user=request.auth, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    if not updated:
        raise HttpError(404, "Token not found.")
    logger.info("api token revoked: user=%s id=%s", request.auth.username, token_id)
    audit_log(request, "auth.api_token_revoked", user=request.auth, token_id=token_id)
    return {"detail": "Token revoked."}

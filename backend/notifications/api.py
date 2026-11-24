"""Owner-scoped notification channel management for the SPA.

Channels live per (user, monitor). Users can add their own Slack/Discord/Telegram
webhook or email address, toggle it, delete it, and send a test message without
waiting for a real outage.
"""

import logging
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from accounts.auth import AuthBearer
from audit.services import audit_log
from config.throttling import MonitorAuthThrottle
from core.net import validate_target_url
from monitors.models import Monitor

from .models import MonitorNotificationChannel

logger = logging.getLogger("notifications")

router = Router(auth=AuthBearer())

KIND_PATTERN = "^(email|webhook|slack|discord|telegram)$"


class ChannelIn(Schema):
    monitor_id: int
    kind: str = Field(pattern=KIND_PATTERN)
    address: str = Field(min_length=1, max_length=500)
    enabled: bool = True


class ChannelUpdateIn(Schema):
    address: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ChannelOut(Schema):
    id: int
    monitor_id: int
    monitor_name: str
    kind: str
    address: str
    enabled: bool
    created_at: datetime


class ChannelTestOut(Schema):
    detail: str
    last_error: str = ""


def _serialize(channel) -> dict:
    return {
        "id": channel.pk,
        "monitor_id": channel.monitor_id,
        "monitor_name": channel.monitor.name,
        "kind": channel.kind,
        "address": channel.address,
        "enabled": channel.enabled,
        "created_at": channel.created_at,
    }


def _validate_address(kind: str, address: str, user) -> str:
    address = address.strip()
    if not address:
        raise HttpError(422, "Address is required.")
    if kind == "email":
        try:
            validate_email(address)
        except ValidationError as exc:
            raise HttpError(422, "Enter a valid email address.") from exc
        # Prevent the platform from being used as a mail relay: notifications may
        # only go to the account's own (verified) address.
        if address.lower() != (user.email or "").lower():
            raise HttpError(422, "Email notifications can only be sent to your account email.")
    elif kind == "telegram":
        token, _, chat_id = address.partition("|")
        if not token or not chat_id:
            raise HttpError(422, "Telegram address must be 'bot_token|chat_id'.")
    else:
        if not address.startswith(("http://", "https://")):
            raise HttpError(422, "Webhook addresses must start with http:// or https://.")
        try:
            address = validate_target_url(address)
        except ValueError as exc:
            raise HttpError(422, str(exc)) from exc
    return address


def _owned_monitor(request, monitor_id: int) -> Monitor:
    monitor = Monitor.objects.filter(pk=monitor_id, owner=request.auth).first()
    if monitor is None:
        raise HttpError(404, "Monitor not found.")
    return monitor


def _owned_channel(request, channel_id: int) -> MonitorNotificationChannel:
    channel = (
        MonitorNotificationChannel.objects.select_related("monitor").filter(pk=channel_id, user=request.auth).first()
    )
    if channel is None:
        raise HttpError(404, "Notification channel not found.")
    return channel


class _TestRow:
    """Minimal stand-in for a NotificationDelivery used by the test endpoint."""

    event_kind = "test"
    payload = {"error": "test notification requested from the dashboard"}

    def __init__(self, monitor):
        self.monitor = monitor


@router.get(
    "/channels",
    response=list[ChannelOut],
    throttle=[MonitorAuthThrottle("200/h")],
    url_name="list_channels",
)
def list_channels(request):
    return [
        _serialize(channel)
        for channel in MonitorNotificationChannel.objects.select_related("monitor")
        .filter(user=request.auth)
        .order_by("-created_at")
    ]


@router.post(
    "/channels",
    response={201: ChannelOut},
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="create_channel",
)
def create_channel(request, payload: ChannelIn):
    monitor = _owned_monitor(request, payload.monitor_id)
    address = _validate_address(payload.kind, payload.address, request.auth)
    if MonitorNotificationChannel.objects.filter(monitor=monitor, kind=payload.kind, address=address).exists():
        raise HttpError(400, "That channel already exists for this monitor.")
    channel = MonitorNotificationChannel.objects.create(
        user=request.auth,
        monitor=monitor,
        kind=payload.kind,
        address=address,
        enabled=payload.enabled,
    )
    logger.info(
        "notification channel created: id=%s user=%s monitor=%s kind=%s",
        channel.pk,
        request.auth.username,
        monitor.pk,
        channel.kind,
    )
    audit_log(
        request,
        "notification.channel_created",
        user=request.auth,
        channel_id=channel.pk,
        monitor_id=monitor.pk,
        channel_kind=channel.kind,
    )
    return 201, _serialize(channel)


@router.patch(
    "/channels/{channel_id}",
    response=ChannelOut,
    throttle=[MonitorAuthThrottle("100/h")],
    url_name="update_channel",
)
def update_channel(request, channel_id: int, payload: ChannelUpdateIn):
    channel = _owned_channel(request, channel_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("address") is not None:
        channel.address = _validate_address(channel.kind, updates["address"], request.auth)
    if updates.get("enabled") is not None:
        channel.enabled = updates["enabled"]
    channel.save(update_fields=["address", "enabled"])
    logger.info("notification channel updated: id=%s user=%s", channel.pk, request.auth.username)
    audit_log(
        request,
        "notification.channel_updated",
        user=request.auth,
        channel_id=channel.pk,
        fields=sorted(updates.keys()),
    )
    return _serialize(channel)


@router.delete(
    "/channels/{channel_id}",
    response={204: None},
    throttle=[MonitorAuthThrottle("100/h")],
    url_name="delete_channel",
)
def delete_channel(request, channel_id: int):
    channel = _owned_channel(request, channel_id)
    monitor_id = channel.monitor.pk
    channel.delete()
    logger.info("notification channel deleted: id=%s user=%s", channel_id, request.auth.username)
    audit_log(
        request,
        "notification.channel_deleted",
        user=request.auth,
        channel_id=channel_id,
        monitor_id=monitor_id,
    )
    return 204, None


@router.post(
    "/channels/{channel_id}/test",
    response=ChannelTestOut,
    throttle=[MonitorAuthThrottle("10/h")],
    url_name="test_channel",
)
def test_channel(request, channel_id: int):
    """Send one synthetic message so the user can verify their endpoint."""
    from .channels import dispatch

    channel = _owned_channel(request, channel_id)
    try:
        dispatch(channel, _TestRow(channel.monitor))
    except Exception as exc:  # report the provider error verbatim
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("notification test failed: id=%s error=%s", channel.pk, error)
        audit_log(
            request,
            "notification.channel_test_failed",
            user=request.auth,
            channel_id=channel.pk,
        )
        return {"detail": "Test message failed.", "last_error": error}

    logger.info("notification test sent: id=%s kind=%s", channel.pk, channel.kind)
    audit_log(
        request,
        "notification.channel_test_sent",
        user=request.auth,
        channel_id=channel.pk,
        channel_kind=channel.kind,
    )
    return {"detail": "Test message delivered.", "last_error": ""}

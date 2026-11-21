from datetime import datetime

from ninja import ModelSchema, Schema
from pydantic import Field

from .models import Monitor


class MonitorIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    url: str = ""
    is_public: bool = True
    check_interval_seconds: int = Field(default=300, ge=60, le=3600)
    kind: str = Field(default="http", pattern="^(http|heartbeat)$")
    heartbeat_grace_seconds: int = Field(default=300, ge=60, le=86400)


class MonitorUpdateIn(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    check_interval_seconds: int | None = Field(default=None, ge=60, le=3600)
    heartbeat_grace_seconds: int | None = Field(default=None, ge=60, le=86400)


class MonitorOut(ModelSchema):
    class Meta:
        model = Monitor
        fields = [
            "id",
            "name",
            "url",
            "is_public",
            "is_active",
            "check_interval_seconds",
            "kind",
            "heartbeat_token",
            "heartbeat_grace_seconds",
            "last_ping_at",
            "last_status",
            "last_status_code",
            "last_response_ms",
            "last_checked_at",
        ]


class PublicMonitorOut(Schema):
    id: int
    name: str
    url: str
    last_status: str
    last_status_code: int | None = None
    last_response_ms: int | None = None
    last_checked_at: datetime | None = None
    uptime_24h: float | None = None


class PublicMonitorDetailOut(PublicMonitorOut):
    uptime_7d: float | None = None
    uptime_30d: float | None = None
    incidents: list["IncidentOut"] = []
    series: list["BucketOut"] = []
    regions: list["RegionOut"] = []


class IncidentOut(Schema):
    id: int
    started_at: datetime
    ended_at: datetime | None = None
    checks_down: int
    last_status_code: int | None = None
    postmortem: str = ""


class MaintenanceOut(Schema):
    id: int
    monitor_id: int
    monitor_name: str
    starts_at: datetime
    ends_at: datetime
    note: str


class MaintenanceIn(Schema):
    starts_at: datetime
    ends_at: datetime
    note: str = ""


class BucketOut(Schema):
    bucket: str
    up_ratio: float
    samples: int


class StatsOut(Schema):
    uptime_percent: float | None
    total_checks: int
    up_checks: int
    series: list[BucketOut]


class RegionOut(Schema):
    region: str
    last_status: str
    last_checked_at: datetime | None = None
    last_response_ms: int | None = None
    uptime_percent: float | None = None


class SslOut(Schema):
    subject: str
    issuer: str
    not_before: datetime | None = None
    not_after: datetime | None = None
    days_remaining: int | None = None
    error: str
    alert_level: str
    checked_at: datetime | None = None


class StatusPageOut(Schema):
    slug: str
    title: str
    description: str
    theme_color: str
    monitors: list[PublicMonitorOut] = []


class HeartbeatOut(Schema):
    detail: str


class PostmortemOut(Schema):
    postmortem: str


class StatusPageIn(Schema):
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=300)
    theme_color: str = Field(default="#0f766e", pattern=r"^#[0-9a-fA-F]{6}$")
    monitor_ids: list[int] = []


class StatusPageUpdateIn(Schema):
    slug: str | None = Field(default=None, min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    theme_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_public: bool | None = None
    is_active: bool | None = None
    monitor_ids: list[int] | None = None


class OwnedStatusPageOut(Schema):
    id: int
    slug: str
    title: str
    description: str
    theme_color: str
    is_public: bool
    is_active: bool
    monitor_ids: list[int] = []

from datetime import datetime

from ninja import ModelSchema, Schema
from pydantic import Field

from .models import Monitor


class MonitorIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    url: str
    is_public: bool = True
    check_interval_seconds: int = Field(default=300, ge=60, le=3600)


class MonitorUpdateIn(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    check_interval_seconds: int | None = Field(default=None, ge=60, le=3600)


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
    series: list["BucketOut"] = []


class BucketOut(Schema):
    bucket: str
    up_ratio: float
    samples: int


class StatsOut(Schema):
    uptime_percent: float | None
    total_checks: int
    up_checks: int
    series: list[BucketOut]

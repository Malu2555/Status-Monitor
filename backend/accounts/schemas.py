from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from datetime import datetime

from ninja import Schema
from pydantic import Field, field_validator


class RegisterIn(Schema):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[\w.@+-]+$")
    email: str
    password: str = Field(min_length=8, max_length=128)
    # Explicit consent — both must be true or registration is refused (400).
    accepted_tos: bool = False
    accepted_age: bool = False
    # Honeypot: real users never see this field, so any value marks a bot.
    company: str = ""

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        try:
            validate_email(value)
        except ValidationError as exc:
            raise ValueError("Enter a valid email address.") from exc
        return value.lower()


class LoginIn(Schema):
    username: str
    password: str
    otp: str | None = None  # required when the account has 2FA enabled


class VerifyEmailIn(Schema):
    token: str


class RequestResetIn(Schema):
    email: str


class ResetConfirmIn(Schema):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class OtpCodeIn(Schema):
    code: str


class OtpEnrollOut(Schema):
    provisioning_uri: str


class OtpActivatedOut(Schema):
    detail: str
    recovery_codes: list[str] = []


class RecoveryCodesSummaryOut(Schema):
    total: int
    unused: int


class UserOut(Schema):
    id: int
    username: str
    email: str
    email_verified: bool
    otp_enabled: bool = False
    plan: str
    plan_label: str
    monitors_used: int
    monitors_limit: int
    subscription_status: str


class TokenOut(Schema):
    access: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserOut


class MessageOut(Schema):
    detail: str


class ApiTokenIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    scope: str = Field(default="write", pattern="^(read|write)$")


class ApiTokenOut(Schema):
    id: int
    name: str
    prefix: str
    scope: str
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked: bool = False


class ApiTokenCreatedOut(Schema):
    id: int
    name: str
    token: str  # plaintext — returned exactly once
    scope: str


class PolicyOut(Schema):
    slug: str
    version: str
    title: str
    body_md: str
    effective_at: datetime


class ModerationIn(Schema):
    reason: str = Field(
        default="manual",
        pattern="^(manual|tos_violation|abuse|chargeback)$",
    )


class ModerationOut(Schema):
    id: int
    username: str
    is_active: bool
    disabled_reason: str = ""
    disabled_at: datetime | None = None
    monitors_paused: int = 0

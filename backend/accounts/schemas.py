from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from ninja import Schema
from pydantic import Field, field_validator


class RegisterIn(Schema):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[\w.@+-]+$")
    email: str
    password: str = Field(min_length=8, max_length=128)

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

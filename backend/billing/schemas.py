from ninja import Schema
from pydantic import Field


class CheckoutIn(Schema):
    plan: str = Field(pattern="^(pro|business)$")


class CheckoutOut(Schema):
    url: str


class BillingSummaryOut(Schema):
    plan: str
    label: str
    monitors_used: int
    monitors_limit: int
    subscription_status: str

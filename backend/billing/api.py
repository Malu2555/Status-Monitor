"""Stripe billing endpoints: checkout, customer portal, verified webhook.

HTTP status codes: 200 OK · 400 unknown plan / missing price / no customer ·
401 missing/invalid access token · 503 Stripe not configured.
Webhook: 200 received · 400 invalid payload/signature · 503 not configured.
"""
import logging

import stripe
from django.conf import settings
from django.http import HttpResponse
from ninja import Router
from ninja.errors import HttpError

from accounts.auth import AuthBearer
from audit.services import audit_log
from config.throttling import MonitorAuthThrottle, PublicAnonThrottle, SessionAuthThrottle

from . import services as billing
from .schemas import BillingSummaryOut, CheckoutIn, CheckoutOut

router = Router(auth=None)

logger = logging.getLogger("billing")


@router.post(
    "/checkout",
    auth=AuthBearer(),
    response=CheckoutOut,
    throttle=[MonitorAuthThrottle("20/h")],
    url_name="billing_checkout",
)
def checkout(request, payload: CheckoutIn):
    logger.info("checkout session requested: user=%s plan=%s", request.auth.username, payload.plan)
    audit_log(request, "billing.checkout_requested", user=request.auth, plan=payload.plan)
    if not request.auth.email_verified:
        raise HttpError(403, "Verify your email address before upgrading.")
    try:
        url = billing.create_checkout_session(request.auth, payload.plan)
    except billing.StripeNotConfigured as exc:
        raise HttpError(503, str(exc)) from exc
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"url": url}


@router.post(
    "/portal",
    auth=AuthBearer(),
    response=CheckoutOut,
    throttle=[MonitorAuthThrottle("20/h")],
    url_name="billing_portal",
)
def portal(request):
    logger.info("billing portal requested: user=%s", request.auth.username)
    audit_log(request, "billing.portal_requested", user=request.auth)
    try:
        url = billing.create_portal_session(request.auth)
    except billing.StripeNotConfigured as exc:
        raise HttpError(503, str(exc)) from exc
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"url": url}


@router.get(
    "/summary",
    auth=AuthBearer(),
    response=BillingSummaryOut,
    throttle=[SessionAuthThrottle("60/m")],
    url_name="billing_summary",
)
def summary(request):
    return billing.get_plan_summary(request.auth)


@router.post("/webhook", auth=None, throttle=[PublicAnonThrottle("30/m")], url_name="stripe_webhook")
def webhook(request):
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse("Stripe webhook verification is not configured.", status=503)
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            request.body, signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.warning("stripe webhook: unreadable payload")
        return HttpResponse("Invalid payload.", status=400)
    except stripe.SignatureVerificationError:
        logger.warning("stripe webhook: signature verification failed")
        return HttpResponse("Invalid signature.", status=400)
    # stripe v15: construct_event returns a stripe.Event (StripeObject, not a dict),
    # so convert it to plain dicts before the dict-based handler uses it.
    event_dict = event.to_dict()
    logger.info("stripe webhook: type=%s id=%s", event_dict["type"], event_dict.get("id"))
    billing.handle_webhook_event(event_dict)
    return HttpResponse("received")

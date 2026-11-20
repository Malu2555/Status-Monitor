# Seed the default Terms of Service and Privacy Policy (version 1.0).
#
# These are deliberately short, plain-language starting points — not legal
# advice. Edit them in the Django admin (or add a new Policy row with a higher
# version) before you take real customers; bump TOS_VERSION in settings when
# the text changes so new registrations stamp the new version.
from django.db import migrations
from django.utils import timezone

TERMS = """# Terms of Service

**Version 1.0**

## 1. The service

Status Monitor checks the availability of URLs you configure and alerts you
through the channels you configure. Checks are best-effort: the free plan gives
no uptime guarantee and no service-level agreement.

## 2. Your account

You are responsible for keeping your credentials and two-factor recovery codes
safe, and for everything that happens under your account or API tokens. You must
be at least 16 years old to create an account.

## 3. Acceptable use

You may only monitor endpoints that you own or are explicitly authorised to
test. You must not use the service to:

- probe, scan or stress hosts you do not control;
- send unsolicited traffic to third parties through webhook or chat channels;
- attempt to bypass plan limits, rate limits or authentication;
- store or transmit unlawful content, or interfere with other customers.

## 4. Billing

Paid plans are sold by Polar.sh as merchant of record. Subscriptions renew
automatically until cancelled; cancelling keeps your plan active until the end
of the paid period. Refunds are handled under Polar's policy.

## 5. Suspension and termination

We may disable an account that violates these terms, abuses the infrastructure
or creates legal risk. Where practical we tell you why. You may delete your
account at any time; we keep limited records (audit log, invoices) as required
by law.

## 6. Liability

The service is provided "as is". To the maximum extent permitted by law we are
not liable for indirect or consequential damages, and our total liability is
limited to the amount you paid us in the previous twelve months.

## 7. Changes

We may update these terms. Material changes are announced in the app and take
effect when you next accept them; the version you accepted is stored on your
account.

## 8. Contact

Questions about these terms: support@statusmonitor.example (replace with your
real address before launch).
"""

PRIVACY = """# Privacy Policy

**Version 1.0**

## What we collect

- **Account data** — username, email address, hashed password, 2FA state, and
  the timestamp/version of the terms you accepted.
- **Monitoring data** — the URLs you add, check results (status, latency,
  errors), incidents, and TLS certificate metadata.
- **Notification destinations** — email addresses, webhook URLs, and
  Telegram `bot_token|chat_id` values you enter, so we can deliver alerts.
- **Audit log** — security- and billing-relevant actions with your user id and
  the originating IP address.

## Why we collect it

To run the checks you configured, to deliver the alerts you asked for, to bill
paid plans, and to keep the service secure.

## Where it lives

Application data is stored in a PostgreSQL database we operate. Passwords are
hashed with Django's password hasher; API tokens and 2FA recovery codes are
stored only as SHA-256 hashes.

## Sharing

- **Polar.sh** processes payments as merchant of record and receives the billing
  details you give it (we never see your card number).
- **Email delivery** goes through the SMTP provider configured for the
  deployment.
- **Slack, Discord and Telegram** messages are delivered by POSTing to the
  endpoints *you* create. We do not read anything back from those services.

We do not sell personal data and we do not run advertising trackers.

## Retention

Checks and audit rows are kept while your account exists and for a short period
after deletion so that invoices and security investigations remain auditable.
Alert destinations are deleted with the monitor they belong to.

## Your rights

You can export your monitoring data as CSV from the dashboard, and you can
request deletion of your account and its data by contacting us. Depending on
where you live (for example GDPR or CCPA) you may also have the right to access,
correct, or port your data.

## Cookies

We set one `httpOnly` refresh-token cookie (scoped to `/api/auth`) and one
readable CSRF cookie. No analytics or advertising cookies are used.

## Contact

Privacy questions: privacy@statusmonitor.example (replace before launch).
"""


def seed_policies(apps, schema_editor):
    Policy = apps.get_model("accounts", "Policy")
    now = timezone.now()
    for slug, title, body in (
        ("terms", "Terms of Service", TERMS),
        ("privacy", "Privacy Policy", PRIVACY),
    ):
        Policy.objects.get_or_create(
            slug=slug,
            version="1.0",
            defaults={"title": title, "body_md": body, "effective_at": now},
        )


def unseed_policies(apps, schema_editor):
    Policy = apps.get_model("accounts", "Policy")
    Policy.objects.filter(slug__in=("terms", "privacy"), version="1.0").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_user_age_confirmed_at_user_disabled_at_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_policies, unseed_policies),
    ]

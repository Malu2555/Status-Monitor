"""Tests for keyword, domain-expiry and broken-link monitoring."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from accounts.services import create_access_token
from monitors.crawling import crawl_monitor
from monitors.models import BrokenLink, Check, CrawlRun, DomainRegistration, Monitor
from monitors.services import check_domain, normalize_domain, run_check
from notifications.models import MonitorNotificationChannel, NotificationDelivery


class TextResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text
        self.headers = {}
        self.content = text.encode()


class KeywordClient:
    text = ""
    status_code = 200

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def get(self, url, headers=None):
        return TextResponse(self.status_code, self.text)


class RdapResponse:
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class RdapClient:
    payload = {}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def get(self, url):
        return RdapResponse(self.payload)


class CoreFeatureTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="featureuser", email="features@example.com", password="Str0ng-Pass!"
        )
        cls.access = create_access_token(cls.user)

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.access}"}

    def make_monitor(self, kind, *, config=None, url="https://example.com"):
        return Monitor.objects.create(
            owner=self.user,
            name=f"{kind} monitor",
            url=url,
            kind=kind,
            config=config or {},
            check_interval_seconds=86400 if kind in ("domain", "broken_links") else 300,
        )

    def create_api_monitor(self, payload):
        return self.client.post(
            "/api/monitors",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth(),
        )


class KeywordMonitorTests(CoreFeatureTestBase):
    def test_create_keyword_monitor(self):
        with patch("monitors.api.validate_target_url", side_effect=lambda url: url):
            response = self.create_api_monitor(
                {
                    "name": "Product page",
                    "url": "https://example.com/product",
                    "kind": "keyword",
                    "config": {
                        "keyword": "Add to cart",
                        "match": "contains",
                        "case_sensitive": False,
                    },
                }
            )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["kind"], "keyword")
        self.assertEqual(body["config"]["keyword"], "Add to cart")

    def test_keyword_contains_passes(self):
        monitor = self.make_monitor("keyword", config={"keyword": "Add to cart"})
        KeywordClient.text = "Big sale — add to cart now!"
        with (
            patch("monitors.services.httpx.Client", KeywordClient),
            patch("monitors.services.validate_target_url", side_effect=lambda url: url),
        ):
            result = run_check(monitor)
        self.assertTrue(result["is_up"])
        self.assertTrue(result["detail"]["found"])
        monitor.refresh_from_db()
        self.assertEqual(monitor.last_status, Monitor.Status.UP)

    def test_keyword_missing_fails(self):
        monitor = self.make_monitor("keyword", config={"keyword": "Add to cart"})
        KeywordClient.text = "Product is unavailable"
        with (
            patch("monitors.services.httpx.Client", KeywordClient),
            patch("monitors.services.validate_target_url", side_effect=lambda url: url),
        ):
            result = run_check(monitor)
        self.assertFalse(result["is_up"])
        self.assertIn("Keyword not found", result["error"])
        self.assertFalse(result["detail"]["found"])
        self.assertEqual(Check.objects.filter(monitor=monitor).count(), 1)

    def test_keyword_not_contains_fails_when_present(self):
        monitor = self.make_monitor("keyword", config={"keyword": "Out of stock", "match": "not_contains"})
        KeywordClient.text = "Out of stock"
        with (
            patch("monitors.services.httpx.Client", KeywordClient),
            patch("monitors.services.validate_target_url", side_effect=lambda url: url),
        ):
            result = run_check(monitor)
        self.assertFalse(result["is_up"])
        self.assertIn("Unexpected keyword", result["error"])


class DomainMonitorTests(CoreFeatureTestBase):
    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("https://Example.com/path"), "example.com")
        self.assertEqual(normalize_domain("example.com"), "example.com")
        self.assertEqual(normalize_domain("münich.de"), "xn--mnich-kva.de")
        for bad in ("", "localhost", "127.0.0.1", "bad domain.com"):
            with self.assertRaises(ValueError):
                normalize_domain(bad)

    def test_check_domain_persists_rdap(self):
        monitor = self.make_monitor("domain", config={"domain": "example.com"})
        expiry = (datetime.now(UTC) + timedelta(days=20)).isoformat().replace("+00:00", "Z")
        RdapClient.payload = {
            "events": [{"eventAction": "expiration", "eventDate": expiry}],
            "entities": [
                {
                    "roles": ["registrar"],
                    "vcardArray": ["vcard", [["fn", {}, "text", "Example Registrar"]]],
                }
            ],
            "status": ["active"],
        }
        with patch("monitors.services.httpx.Client", RdapClient):
            result = check_domain(monitor)
        self.assertEqual(result["domain"], "example.com")
        self.assertEqual(result["registrar"], "Example Registrar")
        self.assertIn(result["days_remaining"], (19, 20))
        record = DomainRegistration.objects.get(monitor=monitor)
        self.assertEqual(record.status, "expiring")

        response = self.client.get(f"/api/monitors/{monitor.pk}/domain", **self.auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["domain"], "example.com")
        self.assertEqual(body["status"], "expiring")
        self.assertEqual(body["registrar"], "Example Registrar")

    def test_domain_command_alerts_once(self):
        monitor = self.make_monitor("domain", config={"domain": "example.com"})
        MonitorNotificationChannel.objects.create(
            user=self.user, monitor=monitor, kind="email", address="ops@example.com"
        )
        expiry = (datetime.now(UTC) + timedelta(days=20)).isoformat().replace("+00:00", "Z")
        RdapClient.payload = {
            "events": [{"eventAction": "expiration", "eventDate": expiry}],
            "entities": [],
        }
        with patch("monitors.services.httpx.Client", RdapClient):
            call_command("check_domains", verbosity=0)
            call_command("check_domains", verbosity=0)
        self.assertEqual(NotificationDelivery.objects.filter(event_kind="domain").count(), 1)
        self.assertEqual(DomainRegistration.objects.get(monitor=monitor).alert_level, "warn")


class CrawlResponse:
    def __init__(self, status_code=200, text="", content_type="text/html"):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}


class CrawlClient:
    bad_status = 404

    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        pass

    def get(self, url, headers=None):
        if url.endswith("/robots.txt"):
            return CrawlResponse(404, "", "text/plain")
        if url.endswith("/bad"):
            return CrawlResponse(self.bad_status, "", "text/html")
        if url.rstrip("/") == "https://example.com":
            return CrawlResponse(
                200,
                '<a href="/ok">ok</a> <a href="/bad">bad</a> <a href="https://external.test/x">x</a>',
            )
        return CrawlResponse(200, "<html><body>fine</body></html>")

    def head(self, url, headers=None):
        if url.endswith("/bad"):
            return CrawlResponse(self.bad_status, "", "text/plain")
        return CrawlResponse(200, "", "text/plain")


class BrokenLinkCrawlTests(CoreFeatureTestBase):
    def crawl(self, monitor):
        with (
            patch("monitors.crawling.httpx.Client", CrawlClient),
            patch("monitors.crawling.validate_target_url", side_effect=lambda url: url),
        ):
            return crawl_monitor(monitor, max_seconds=5)

    def test_crawl_records_and_resolves_broken_link(self):
        monitor = self.make_monitor("broken_links", config={"max_pages": 5, "max_depth": 1, "check_images": True})
        CrawlClient.bad_status = 404
        summary = self.crawl(monitor)
        self.assertEqual(summary["broken_count"], 1)
        self.assertEqual(summary["new_count"], 1)
        self.assertEqual(CrawlRun.objects.filter(monitor=monitor).count(), 1)
        link = BrokenLink.objects.get(monitor=monitor)
        self.assertTrue(link.target_url.endswith("/bad"))
        monitor.refresh_from_db()
        self.assertEqual(monitor.last_status, Monitor.Status.UP)

        response = self.client.get(f"/api/monitors/{monitor.pk}/crawl", **self.auth())
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["run"]["broken_count"], 1)
        self.assertEqual(len(report["broken_links"]), 1)

        CrawlClient.bad_status = 200
        summary = self.crawl(monitor)
        self.assertEqual(summary["broken_count"], 0)
        link.refresh_from_db()
        self.assertIsNotNone(link.resolved_at)
        self.assertEqual(Check.objects.filter(monitor=monitor).count(), 2)

    def test_create_domain_and_broken_link_monitors_default_to_daily(self):
        with patch("monitors.api.validate_target_url", side_effect=lambda url: url):
            domain = self.create_api_monitor(
                {
                    "name": "Acme domain",
                    "url": "acme.com",
                    "kind": "domain",
                    "config": {"domain": "acme.com"},
                }
            )
        self.assertEqual(domain.status_code, 201)
        self.assertEqual(domain.json()["url"], "https://acme.com")
        self.assertEqual(domain.json()["check_interval_seconds"], 86400)
        self.assertEqual(domain.json()["config"]["domain"], "acme.com")

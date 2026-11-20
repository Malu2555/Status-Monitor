"""Application-level DoS guard: honeypot, IP blocking, trusted-proxy parsing."""
import json
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from accounts import abuse
from accounts.models import AbuseEvent, BlockedIP, User


class HoneypotTests(TestCase):
    def setUp(self):
        cache.clear()

    def _register(self, **overrides):
        payload = {
            "username": "hpot",
            "email": "hpot@example.com",
            "password": "Str0ng-Pass!",
            "accepted_tos": True,
            "accepted_age": True,
            "company": "",
            **overrides,
        }
        return self.client.post(
            "/api/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_honeypot_rejects_registration(self):
        resp = self._register(company="Acme Inc")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertTrue(AbuseEvent.objects.filter(kind="honeypot").exists())

    def test_empty_honeypot_allows_registration(self):
        resp = self._register()
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(AbuseEvent.objects.filter(kind="honeypot").exists())


class BlockedIPTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_blocked_ip_is_refused_before_routing(self):
        BlockedIP.objects.create(ip="127.0.0.1", reason="test")
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Access denied.")

    def test_expired_block_is_ignored_and_removed(self):
        BlockedIP.objects.create(
            ip="127.0.0.1",
            reason="old",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(BlockedIP.objects.filter(ip="127.0.0.1").exists())

    def test_auto_block_after_threshold(self):
        ip = "127.0.0.1"
        for _ in range(abuse.AUTO_BLOCK_THRESHOLD - 1):
            self.assertFalse(abuse.note_failure(ip, "login"))
        self.assertTrue(abuse.note_failure(ip, "login"))

        row = BlockedIP.objects.get(ip=ip)
        self.assertTrue(row.auto)
        self.assertIsNotNone(row.expires_at)
        self.assertEqual(self.client.get("/api/health").status_code, 403)

    def test_failed_logins_feed_the_counter(self):
        resp = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "nobody", "password": "wrong-pass"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(AbuseEvent.objects.filter(kind="login").exists())


class TrustedProxyTests(TestCase):
    class _Request:
        def __init__(self, meta):
            self.META = meta

    def test_forwarded_header_ignored_from_untrusted_peer(self):
        request = self._Request({"REMOTE_ADDR": "203.0.113.9", "HTTP_X_FORWARDED_FOR": "1.2.3.4"})
        self.assertEqual(abuse.client_ip(request), "203.0.113.9")

    def test_forwarded_header_used_from_trusted_proxy(self):
        request = self._Request({"REMOTE_ADDR": "127.0.0.1", "HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8"})
        self.assertEqual(abuse.client_ip(request), "1.2.3.4")

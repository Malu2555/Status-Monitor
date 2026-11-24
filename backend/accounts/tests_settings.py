"""Startup configuration guards: signing-key length and production fail-fast."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase

from accounts.models import User
from accounts.services import issue_token_pair, safe_decode_token
from config.env_checks import DEV_SECRET_KEY, MIN_SECRET_KEY_LENGTH, validate_secret_key


class SigningKeyTests(SimpleTestCase):
    def test_effective_signing_key_is_long_enough_for_hs256(self):
        self.assertGreaterEqual(len(settings.JWT_SIGNING_KEY.encode()), 32)

    def test_dev_default_key_is_long_enough_for_hs256_and_django(self):
        self.assertGreaterEqual(len(DEV_SECRET_KEY.encode()), 32)
        self.assertGreaterEqual(len(DEV_SECRET_KEY), MIN_SECRET_KEY_LENGTH)

    def test_production_rejects_the_dev_default(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_secret_key(DEV_SECRET_KEY, debug=False)

    def test_production_rejects_short_keys(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_secret_key("x" * (MIN_SECRET_KEY_LENGTH - 1), debug=False)

    def test_production_accepts_a_long_key(self):
        validate_secret_key("x" * MIN_SECRET_KEY_LENGTH, debug=False)

    def test_debug_accepts_any_key(self):
        validate_secret_key("short", debug=True)


class TokenRoundTripTests(TestCase):
    def test_access_token_round_trips_with_the_configured_key(self):
        user = User.objects.create_user("keycheck", "keycheck@example.com", "Str0ng-Pass!")
        access, _refresh = issue_token_pair(user)
        payload = safe_decode_token(access, "access")
        self.assertIsNotNone(payload)
        assert payload is not None  # narrows the type for pyright
        self.assertEqual(str(payload["sub"]), str(user.pk))

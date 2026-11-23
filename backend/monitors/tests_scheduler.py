"""Scheduler endpoint + run_scheduler command tests."""

from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from monitors.models import Monitor


@override_settings(SCHEDULER_TOKEN="test-scheduler-token", ADMIN_LOGIN_DELAY_SECONDS=0)
class SchedulerEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        # Keep the sweep off the network: no due monitors.
        Monitor.objects.update(is_active=False)

    def _post(self, job, token=None):
        headers = {"HTTP_X_SCHEDULER_TOKEN": token} if token is not None else {}
        return self.client.post(f"/api/admin/scheduler/{job}", **headers)

    def test_valid_token_runs_the_job(self):
        response = self._post("run-checks", "test-scheduler-token")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["job"], "run-checks")
        self.assertIn("Checked 0 monitor", body["output"])

    def test_missing_or_wrong_token_is_rejected(self):
        self.assertEqual(self._post("run-checks").status_code, 403)
        self.assertEqual(self._post("run-checks", "wrong").status_code, 403)

    @override_settings(SCHEDULER_TOKEN="")
    def test_disabled_when_token_is_not_configured(self):
        self.assertEqual(self._post("run-checks", "anything").status_code, 403)

    def test_unknown_job_is_404(self):
        self.assertEqual(self._post("not-a-job", "test-scheduler-token").status_code, 404)


class RunSchedulerCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        Monitor.objects.update(is_active=False)

    def test_once_all_runs_minute_and_daily_jobs(self):
        output = StringIO()
        call_command("run_scheduler", "--once", "--all", stdout=output)
        text = output.getvalue()
        self.assertIn("[scheduler] run_checks", text)
        self.assertIn("[scheduler] deliver_notifications", text)
        self.assertIn("[scheduler] prune_history", text)
        self.assertIn("[scheduler] check_ssl", text)
        self.assertIn("[scheduler] check_domains", text)
        self.assertIn("[scheduler] crawl_links", text)

    def test_unknown_job_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("run_scheduler", "--once", "--jobs", "definitely-not-a-job")

    def test_daily_jobs_are_not_repeated_the_same_day(self):
        first = StringIO()
        call_command("run_scheduler", "--once", "--all", stdout=first)
        second = StringIO()
        call_command("run_scheduler", "--once", "--all", stdout=second)
        self.assertIn("check_ssl", first.getvalue())
        self.assertNotIn("[scheduler] check_ssl", second.getvalue())

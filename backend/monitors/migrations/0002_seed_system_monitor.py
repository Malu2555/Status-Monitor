"""Seed the operator's own website as a system monitor (SELF_MONITOR_URL)."""

from django.conf import settings
from django.db import migrations


def seed_system_monitor(apps, schema_editor):
    Monitor = apps.get_model("monitors", "Monitor")
    url = getattr(settings, "SELF_MONITOR_URL", "")
    if not url:
        return
    if Monitor.objects.filter(is_system=True).exists():
        return
    Monitor.objects.create(
        name=getattr(settings, "SELF_MONITOR_NAME", "My site") or "My site",
        url=url,
        is_public=True,
        is_active=True,
        is_system=True,
        check_interval_seconds=300,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("monitors", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_system_monitor, migrations.RunPython.noop),
    ]

from django.conf import settings
from django.db import models


class Monitor(models.Model):
    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        UP = "up", "Up"
        DOWN = "down", "Down"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="monitors",
    )
    name = models.CharField(max_length=100)
    url = models.CharField(max_length=500)
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False, editable=False)
    check_interval_seconds = models.PositiveIntegerField(default=300)

    # "http" probes a URL; "heartbeat" waits for inbound pings; "keyword"
    # asserts page content; "domain" tracks registrar expiry; "broken_links"
    # crawls a site for dead links.
    kind = models.CharField(
        max_length=20,
        choices=[
            ("http", "HTTP"),
            ("heartbeat", "Heartbeat"),
            ("keyword", "Keyword / content"),
            ("domain", "Domain expiry"),
            ("broken_links", "Broken links"),
        ],
        default="http",
    )
    # Type-specific settings (keyword phrase, domain name, crawl limits, …).
    config = models.JSONField(default=dict, blank=True)
    heartbeat_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    heartbeat_grace_seconds = models.PositiveIntegerField(default=300)
    last_ping_at = models.DateTimeField(null=True, blank=True)

    last_status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNKNOWN)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_response_ms = models.PositiveIntegerField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_interval_seconds__gte=60),
                name="monitor_interval_min_60",
            )
        ]

    def __str__(self):
        return self.name


class Check(models.Model):
    """One probe result for a monitor."""

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="checks")
    is_up = models.BooleanField()
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    # Per-check extras (keyword match, response size, crawl run id, …).
    detail = models.JSONField(default=dict, blank=True)
    # Which runner/region produced this probe (multi-region monitoring).
    region = models.CharField(max_length=32, default="local")
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["monitor", "-checked_at"]),
            models.Index(fields=["monitor", "region", "-checked_at"]),
        ]

    def __str__(self):
        return f"{self.monitor.pk} {self.is_up} @ {self.checked_at} ({self.region})"


class Incident(models.Model):
    """A contiguous outage: opened on a down transition, closed on recovery."""

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="incidents")
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    checks_down = models.PositiveIntegerField(default=1)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    # Customer-facing postmortem draft (generated from the incident timeline).
    postmortem = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["monitor", "-started_at"])]

    def __str__(self):
        state = "ongoing" if self.ended_at is None else f"resolved {self.ended_at:%Y-%m-%d}"
        return f"{self.monitor} down since {self.started_at:%Y-%m-%d} ({state})"


class MaintenanceWindow(models.Model):
    """Planned downtime — down checks inside the window don't trigger alerts."""

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="maintenance_windows")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]
        indexes = [models.Index(fields=["monitor", "starts_at", "ends_at"])]

    def __str__(self):
        return f"{self.monitor} maintenance {self.starts_at:%m-%d %H:%M}-{self.ends_at:%m-%d %H:%M}"


class SslCertificate(models.Model):
    """Latest TLS certificate state for one https monitor.

    Populated by ``manage.py check_ssl``. ``alert_level`` deduplicates
    notification escalation: we only enqueue a new alert when the level changes
    ("" → "warn" → "critical"), not on every sweep.
    """

    monitor = models.OneToOneField(Monitor, on_delete=models.CASCADE, related_name="ssl")
    subject = models.CharField(max_length=255, blank=True, default="")
    issuer = models.CharField(max_length=255, blank=True, default="")
    not_before = models.DateTimeField(null=True, blank=True)
    not_after = models.DateTimeField(null=True, blank=True)
    days_remaining = models.IntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    alert_level = models.CharField(max_length=10, blank=True, default="")  # ""|warn|critical
    checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-checked_at"]

    def __str__(self):
        suffix = f"{self.days_remaining}d left" if self.days_remaining is not None else self.error
        return f"{self.monitor} TLS ({suffix})"


class DomainRegistration(models.Model):
    """Latest RDAP registration state for one domain-expiry monitor.

    Mirrors ``SslCertificate``: ``alert_level`` deduplicates escalation so the
    daily sweep only queues an alert when the threshold level changes.
    """

    monitor = models.OneToOneField(Monitor, on_delete=models.CASCADE, related_name="domain")
    domain = models.CharField(max_length=255)
    expires_at = models.DateTimeField(null=True, blank=True)
    days_remaining = models.IntegerField(null=True, blank=True)
    registrar = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32, blank=True, default="")  # ok|expiring|expired|unknown
    error = models.TextField(blank=True, default="")
    alert_level = models.CharField(max_length=10, blank=True, default="")  # ""|warn|critical
    checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-checked_at"]

    def __str__(self):
        suffix = f"{self.days_remaining}d left" if self.days_remaining is not None else self.error
        return f"{self.domain} ({suffix})"


class CrawlRun(models.Model):
    """One broken-link crawl of one site."""

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="crawl_runs")
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    pages_crawled = models.PositiveIntegerField(default=0)
    links_checked = models.PositiveIntegerField(default=0)
    broken_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["monitor", "-started_at"])]

    def __str__(self):
        return f"{self.monitor} crawl @ {self.started_at:%Y-%m-%d %H:%M} ({self.broken_count} broken)"


class BrokenLink(models.Model):
    """A dead URL discovered by a crawl, kept until it starts working again."""

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="broken_links")
    run = models.ForeignKey(CrawlRun, on_delete=models.CASCADE, related_name="links")
    source_url = models.CharField(max_length=1000)
    target_url = models.CharField(max_length=1000)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["monitor", "source_url", "target_url"],
                name="unique_monitor_broken_link",
            )
        ]
        indexes = [models.Index(fields=["monitor", "resolved_at"])]

    def __str__(self):
        return f"{self.monitor}: {self.target_url} ({self.status_code or self.error[:40]})"


class StatusPage(models.Model):
    """A branded public page showing a chosen subset of monitors.

    Rendering lives at ``GET /api/public/statuspages/{slug}`` and the SPA route
    ``/p/:slug``. Pages are managed in the Django admin (owner + monitors are
    editable there), keeping the write surface small.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="status_pages",
    )
    slug = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True, default="")
    theme_color = models.CharField(max_length=7, blank=True, default="#0f766e")
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    monitors = models.ManyToManyField(Monitor, related_name="status_pages", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} (/p/{self.slug})"

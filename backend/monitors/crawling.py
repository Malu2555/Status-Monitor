"""Broken-link crawler for ``kind="broken_links"`` monitors.

Same-origin BFS with robots.txt, SSRF re-validation on every hop, a page
budget, and a wall-clock budget so it can run through the HTTP cron path.
Only server-rendered HTML is inspected (no JS execution).
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from django.conf import settings
from django.utils import timezone

from .models import BrokenLink, CrawlRun, Monitor
from .services import record_check_result, validate_target_url

logger = logging.getLogger("monitors")

USER_AGENT = "StatusMonitor/1.0 (+broken-link-check)"
PAGE_BYTE_CAP = 2_000_000
MAX_LINK_CHECKS = 500


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme, (parts.hostname or "").lower(), port


def _same_origin(url: str, origin: tuple[str, str, int]) -> bool:
    return _origin(url) == origin


def _normalize(raw: str, base: str) -> str:
    if not raw or raw.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return ""
    try:
        joined = urljoin(base, raw.strip())
    except ValueError:
        return ""
    parts = urlsplit(joined)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    return urldefrag(joined)[0]


def _robots_for(client: httpx.Client, start_url: str) -> RobotFileParser | None:
    parts = urlsplit(start_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        validate_target_url(robots_url)
        response = client.get(robots_url, headers={"User-Agent": USER_AGENT})
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(str(response.text).splitlines())
        return parser
    except (httpx.HTTPError, ValueError, OSError):
        return None


def _fetch_page(client: httpx.Client, url: str, robots: RobotFileParser | None) -> tuple[int | None, str]:
    """Fetch one HTML page, following redirects with SSRF validation."""
    current = url
    try:
        for _ in range(settings.CHECK_MAX_REDIRECTS + 1):
            current = validate_target_url(current)
            if robots is not None and not robots.can_fetch(USER_AGENT, current):
                return None, ""
            response = client.get(current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if location:
                    current = urljoin(current, location)
                    continue
            content_type = response.headers.get("content-type", "")
            text = str(response.text)[:PAGE_BYTE_CAP] if "html" in content_type else ""
            return response.status_code, text
    except (httpx.HTTPError, ValueError, OSError) as exc:
        logger.info("crawl page failed: %s (%s)", url, str(exc)[:120])
    return None, ""


def _check_link(client: httpx.Client, url: str) -> tuple[int | None, str, bool]:
    """Return (status_code, error, skipped). skipped=True means SSRF-blocked."""
    try:
        validate_target_url(url)
    except ValueError:
        return None, "", True
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    try:
        response = client.head(url, headers=headers)
        if response.status_code in (403, 405, 501):
            response = client.get(url, headers=headers)
        if 200 <= response.status_code < 400:
            return response.status_code, "", False
        return response.status_code, f"HTTP {response.status_code}", False
    except (httpx.HTTPError, OSError) as exc:
        return None, str(exc)[:200], False


def _extract_links(text: str, page_url: str, check_images: bool) -> list[str]:
    soup = BeautifulSoup(text, "html.parser")
    raw_links = [anchor.get("href") for anchor in soup.find_all("a", href=True)]
    if check_images:
        raw_links += [image.get("src") for image in soup.find_all("img", src=True)]
    links: list[str] = []
    for raw in raw_links:
        target = _normalize(str(raw), page_url)
        if target:
            links.append(target)
    return links


def crawl_monitor(monitor: Monitor, max_seconds: int | None = None) -> dict:
    """Crawl a site and persist its broken links.

    Returns a summary dict and records one Check row (up = start page fetched).
    Newly broken URLs enqueue one notification per channel; resolved URLs are
    closed automatically.
    """
    config = monitor.config or {}
    max_pages = min(max(int(config.get("max_pages", 25)), 1), 100)
    max_depth = min(max(int(config.get("max_depth", 2)), 1), 3)
    check_images = bool(config.get("check_images", False))
    check_external = bool(config.get("check_external", False))
    start_url = validate_target_url(monitor.url)
    origin = _origin(start_url)
    run = CrawlRun.objects.create(monitor=monitor)
    started = time.monotonic()
    deadline = started + (max_seconds or settings.CRAWL_MAX_SECONDS)
    start_status: int | None = None
    start_ok = False
    start_error = ""
    pages: list[str] = []
    targets: dict[str, set[str]] = {}
    page_failures: dict[str, tuple[int | None, str]] = {}
    queue: list[tuple[str, int]] = [(start_url, 0)]
    seen: set[str] = set()

    client = httpx.Client(
        timeout=min(settings.CHECK_TIMEOUT_SECONDS, 10),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        robots = _robots_for(client, start_url)
        while queue and len(pages) < max_pages and time.monotonic() < deadline:
            page_url, depth = queue.pop(0)
            if page_url in seen:
                continue
            seen.add(page_url)
            status, text = _fetch_page(client, page_url, robots)
            if status is None:
                page_failures[page_url] = (None, "The page could not be fetched.")
                if page_url == start_url:
                    start_error = "The start page could not be fetched."
                continue
            pages.append(page_url)
            if page_url == start_url:
                start_status = status
                start_ok = 200 <= status < 400
                if not start_ok:
                    start_error = f"HTTP {status}"
            elif status >= 400:
                page_failures[page_url] = (status, f"HTTP {status}")
            if not text:
                continue
            for target in _extract_links(text, page_url, check_images):
                if not check_external and not _same_origin(target, origin):
                    continue
                targets.setdefault(target, set()).add(page_url)
                if _same_origin(target, origin) and depth < max_depth and target not in seen:
                    queue.append((target, depth + 1))

        to_check = sorted(target for target in targets if target not in seen)[:MAX_LINK_CHECKS]
        completed = not queue and len(pages) < max_pages and time.monotonic() < deadline
        broken: dict[tuple[str, str], tuple[int | None, str]] = {}
        if start_ok and to_check:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(_check_link, client, target): target for target in to_check}
                for future, target in futures.items():
                    status, error, skipped = future.result()
                    if skipped or status is None or 200 <= status < 400:
                        continue
                    for source in targets[target]:
                        broken[(source, target)] = (status, error)
        for failed_url, (status, error) in page_failures.items():
            for source in targets.get(failed_url, set()):
                broken[(source, failed_url)] = (status, error)
    finally:
        client.close()

    previous = {
        (link.source_url, link.target_url): link
        for link in BrokenLink.objects.filter(monitor=monitor, resolved_at__isnull=True)
    }
    new_links: list[dict] = []
    now = timezone.now()
    for (source, target), (status, error) in broken.items():
        _, created = BrokenLink.objects.update_or_create(
            monitor=monitor,
            source_url=source,
            target_url=target,
            defaults={
                "run": run,
                "status_code": status,
                "error": error,
                "resolved_at": None,
            },
        )
        if created or (source, target) not in previous:
            new_links.append({"target_url": target, "status_code": status, "error": error, "source_url": source})
    for key, link in previous.items():
        if start_ok and completed and key not in broken:
            link.resolved_at = now
            link.save(update_fields=["resolved_at"])

    run.finished_at = timezone.now()
    run.pages_crawled = len(pages)
    run.links_checked = len(to_check)
    run.broken_count = len(broken)
    run.error = start_error
    run.save(update_fields=["finished_at", "pages_crawled", "links_checked", "broken_count", "error"])

    elapsed_ms = int((time.monotonic() - started) * 1000)
    record_check_result(
        monitor,
        is_up=start_ok,
        status_code=start_status,
        response_ms=elapsed_ms,
        error=start_error,
        detail={
            "crawl_run_id": run.pk,
            "pages_crawled": len(pages),
            "links_checked": len(to_check),
            "broken_count": len(broken),
        },
    )
    if start_ok and new_links:
        from notifications.services import enqueue_broken_links_alert

        enqueue_broken_links_alert(monitor, len(new_links), new_links)
    logger.info(
        "crawl: monitor=%s pages=%s links=%s broken=%s new=%s",
        monitor.pk,
        len(pages),
        len(to_check),
        len(broken),
        len(new_links),
    )
    return {
        "run_id": run.pk,
        "pages_crawled": len(pages),
        "links_checked": len(to_check),
        "broken_count": len(broken),
        "new_count": len(new_links),
        "error": start_error,
    }

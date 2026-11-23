"""Outbound network safety: SSRF guard and a conservative HTTP client.

Every server-side request to a user-supplied URL (monitors, crawls, notification
webhooks) must go through this module. It rejects non-HTTP schemes, resolves the
hostname and requires every resolved address to be globally routable, which
blocks loopback, private ranges, link-local/metadata endpoints and multicast.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


def validate_target_url(url: str) -> str:
    """Validate that ``url`` is an http(s) URL resolving only to public IPs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http:// and https:// URLs are allowed.")
    host = parsed.hostname
    if not host:
        raise ValueError("The URL must include a hostname.")
    host = host.strip("[]")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError("The hostname could not be resolved.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("URLs pointing to private, loopback or internal networks are not allowed.")
    return parsed.geturl()


def safe_post(url: str, *, json=None, headers=None, timeout: float = 10.0):
    """POST to a validated public URL; never follow redirects automatically.

    The URL is re-validated immediately before the request so a hostname that
    changed its DNS answer after creation time is still rejected.
    """
    validate_target_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.post(url, json=json, headers=headers)
        response.raise_for_status()
        return response

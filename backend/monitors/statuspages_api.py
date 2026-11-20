"""Authenticated CRUD for custom status pages (owner-scoped).

Mounted at ``/api/statuspages``. Public rendering is
``GET /api/public/statuspages/{slug}`` (see ``monitors.api``).
"""
import logging

from ninja import Router, Status
from ninja.errors import HttpError

from accounts.auth import ApiKeyAuth, AuthBearer
from audit.services import audit_log
from config.throttling import MonitorAuthThrottle

from .models import Monitor, StatusPage
from .schemas import OwnedStatusPageOut, StatusPageIn, StatusPageUpdateIn

router = Router(auth=[AuthBearer(), ApiKeyAuth()])
logger = logging.getLogger("monitors")


def _owned_or_404(request, page_id: int) -> StatusPage:
    page = StatusPage.objects.filter(pk=page_id, owner=request.auth).first()
    if page is None:
        raise HttpError(404, "Status page not found.")
    return page


def _require_write(request) -> None:
    if getattr(request, "api_token_scope", "write") == "read":
        raise HttpError(403, "This API token is read-only.")


def _out(page: StatusPage) -> OwnedStatusPageOut:
    return OwnedStatusPageOut(
        id=page.pk,
        slug=page.slug,
        title=page.title,
        description=page.description,
        theme_color=page.theme_color,
        is_public=page.is_public,
        is_active=page.is_active,
        monitor_ids=list(page.monitors.values_list("pk", flat=True)),
    )


def _apply_monitors(page: StatusPage, monitor_ids: list[int]) -> None:
    page.monitors.set(Monitor.objects.filter(owner=page.owner, pk__in=monitor_ids))


@router.get(
    "",
    response=list[OwnedStatusPageOut],
    throttle=[MonitorAuthThrottle("120/h")],
    url_name="statuspage_list",
)
def list_status_pages(request):
    pages = StatusPage.objects.filter(owner=request.auth).prefetch_related("monitors")
    return [_out(page) for page in pages]


@router.post(
    "",
    response={201: OwnedStatusPageOut},
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="statuspage_create",
)
def create_status_page(request, payload: StatusPageIn):
    _require_write(request)
    if StatusPage.objects.filter(slug=payload.slug).exists():
        raise HttpError(400, "That slug is already taken.")
    page = StatusPage.objects.create(
        owner=request.auth,
        slug=payload.slug,
        title=payload.title.strip(),
        description=payload.description,
        theme_color=payload.theme_color,
    )
    _apply_monitors(page, payload.monitor_ids)
    logger.info("status page created: id=%s user=%s", page.pk, request.auth.username)
    audit_log(request, "statuspage.create", user=request.auth, page_id=page.pk, slug=page.slug)
    return _out(page)


@router.get(
    "/{page_id}",
    response=OwnedStatusPageOut,
    throttle=[MonitorAuthThrottle("120/h")],
    url_name="statuspage_get",
)
def get_status_page(request, page_id: int):
    return _out(_owned_or_404(request, page_id))


@router.patch(
    "/{page_id}",
    response=OwnedStatusPageOut,
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="statuspage_update",
)
def update_status_page(request, page_id: int, payload: StatusPageUpdateIn):
    page = _owned_or_404(request, page_id)
    _require_write(request)
    updates = payload.model_dump(exclude_unset=True)
    monitor_ids = updates.pop("monitor_ids", None)
    if (
        "slug" in updates
        and StatusPage.objects.filter(slug=updates["slug"]).exclude(pk=page.pk).exists()
    ):
        raise HttpError(400, "That slug is already taken.")
    for field, value in updates.items():
        setattr(page, field, value)
    page.save()
    if monitor_ids is not None:
        _apply_monitors(page, monitor_ids)
    logger.info("status page updated: id=%s user=%s", page.pk, request.auth.username)
    audit_log(
        request,
        "statuspage.update",
        user=request.auth,
        page_id=page.pk,
        fields=sorted(updates.keys()),
    )
    return _out(page)


@router.delete(
    "/{page_id}",
    response={204: None},
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="statuspage_delete",
)
def delete_status_page(request, page_id: int):
    page = _owned_or_404(request, page_id)
    _require_write(request)
    page_pk = page.pk
    page.delete()
    logger.info("status page deleted: id=%s user=%s", page_pk, request.auth.username)
    audit_log(request, "statuspage.delete", user=request.auth, page_id=page_pk)
    return Status(204, None)

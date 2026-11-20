"""Public legal-text endpoints (terms / privacy).

Unauthenticated by design: the SPA renders these before login, and the
registration form links to them.
"""
from ninja import Router

from . import services as auth_services
from .schemas import PolicyOut

router = Router(auth=None)


@router.get("/{slug}", response=PolicyOut, url_name="policy_get")
def get_policy(request, slug: str):
    policy = auth_services.current_policy(slug)
    if policy is None:
        from ninja.errors import HttpError

        raise HttpError(404, "Policy not found.")
    return {
        "slug": policy.slug,
        "version": policy.version,
        "title": policy.title,
        "body_md": policy.body_md,
        "effective_at": policy.effective_at,
    }

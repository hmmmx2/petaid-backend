"""Role-based access control — the permission matrix (single source of truth).

PetAid has two roles (the ``Account.role`` discriminator in
``app.models.account``): ``pet_owner`` and ``veterinary_expert``. This module
defines *what each role may do* as an explicit, auditable mapping, instead of
the access rules being scattered across routers as ad-hoc ``isinstance`` checks.

Two complementary layers exist in the codebase:

1. **RBAC (this module)** — "may this role perform this action at all?"
   Enforced declaratively via :func:`app.api.deps.require`.
2. **Object-level / ABAC** — "does this user own / participate in *this*
   object?" Enforced by per-row query filters and ``_assert_participant`` in the
   routers (unchanged). Both layers apply together (defence in depth).
"""
from __future__ import annotations

import enum


class Permission(str, enum.Enum):
    """A single capability. ``str`` mixin so values JSON-serialise as-is."""

    DASHBOARD_VIEW = "dashboard:view"

    # Pets
    PET_MANAGE = "pet:manage"          # create / list / delete own pets
    PET_TYPE_MANAGE = "pet_type:manage"

    # Resources & guidance
    RESOURCE_VIEW = "resource:view"
    RESOURCE_MANAGE = "resource:manage"  # create / publish
    GUIDANCE_AUTHOR = "guidance:author"

    # Quizzes
    QUIZ_VIEW = "quiz:view"
    QUIZ_TAKE = "quiz:take"            # submit / list own attempts
    QUIZ_AUTHOR = "quiz:author"

    # Inquiries
    INQUIRY_VIEW = "inquiry:view"
    INQUIRY_CREATE = "inquiry:create"
    INQUIRY_RESPOND = "inquiry:respond"
    INQUIRY_CLOSE = "inquiry:close"

    # Chats
    CHAT_VIEW = "chat:view"
    CHAT_INITIATE = "chat:initiate"
    CHAT_JOIN = "chat:join"
    CHAT_PARTICIPATE = "chat:participate"  # post message / close as participant

    # Donations
    DONATION_VIEW = "donation:view"
    DONATION_CREATE = "donation:create"

    # Feedback
    FEEDBACK_SUBMIT = "feedback:submit"
    FEEDBACK_REVIEW = "feedback:review"

    # MFA
    MFA_ENROLL = "mfa:enroll"


# Role discriminator strings must match app.models.account.Account.role.
ROLE_PET_OWNER = "pet_owner"
ROLE_VET = "veterinary_expert"

_PET_OWNER_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.DASHBOARD_VIEW,
        Permission.PET_MANAGE,
        Permission.RESOURCE_VIEW,
        Permission.QUIZ_VIEW,
        Permission.QUIZ_TAKE,
        Permission.INQUIRY_VIEW,
        Permission.INQUIRY_CREATE,
        Permission.INQUIRY_CLOSE,
        Permission.CHAT_VIEW,
        Permission.CHAT_INITIATE,
        Permission.CHAT_PARTICIPATE,
        Permission.DONATION_VIEW,
        Permission.DONATION_CREATE,
        Permission.FEEDBACK_SUBMIT,
    }
)

_VET_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.DASHBOARD_VIEW,
        Permission.PET_TYPE_MANAGE,
        Permission.RESOURCE_VIEW,
        Permission.RESOURCE_MANAGE,
        Permission.GUIDANCE_AUTHOR,
        Permission.QUIZ_VIEW,
        Permission.QUIZ_AUTHOR,
        Permission.INQUIRY_VIEW,
        Permission.INQUIRY_RESPOND,
        Permission.INQUIRY_CLOSE,
        Permission.CHAT_VIEW,
        Permission.CHAT_JOIN,
        Permission.CHAT_PARTICIPATE,
        Permission.DONATION_VIEW,
        Permission.FEEDBACK_REVIEW,
        Permission.MFA_ENROLL,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    ROLE_PET_OWNER: _PET_OWNER_PERMS,
    ROLE_VET: _VET_PERMS,
}


def permissions_for(role: str | None) -> frozenset[Permission]:
    """Return the permission set granted to ``role`` (empty for unknown roles)."""
    return ROLE_PERMISSIONS.get(role or "", frozenset())


def has_permission(account, permission: Permission) -> bool:
    """True if ``account``'s role grants ``permission``."""
    return permission in permissions_for(getattr(account, "role", None))

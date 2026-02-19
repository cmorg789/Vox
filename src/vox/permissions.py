"""Permission bit flags and resolution algorithm per PROTOCOL.md §7."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.db.models import PermissionOverride, Role, role_members

# --- Bit flags ---

VIEW_SPACE         = 1 << 0
SEND_MESSAGES      = 1 << 1
SEND_EMBEDS        = 1 << 2
ATTACH_FILES       = 1 << 3
ADD_REACTIONS      = 1 << 4
READ_HISTORY       = 1 << 5
MENTION_EVERYONE   = 1 << 6
CONNECT            = 1 << 8
SPEAK              = 1 << 9
VIDEO              = 1 << 10
MUTE_MEMBERS       = 1 << 11
DEAFEN_MEMBERS     = 1 << 12
MOVE_MEMBERS       = 1 << 13
PRIORITY_SPEAKER   = 1 << 14
STREAM             = 1 << 15
STAGE_MODERATOR    = 1 << 16
CREATE_THREADS     = 1 << 17
MANAGE_THREADS     = 1 << 18
SEND_IN_THREADS    = 1 << 19
MANAGE_SPACES      = 1 << 24
MANAGE_ROLES       = 1 << 25
MANAGE_EMOJI       = 1 << 26
MANAGE_WEBHOOKS    = 1 << 27
MANAGE_SERVER      = 1 << 28
KICK_MEMBERS       = 1 << 29
BAN_MEMBERS        = 1 << 30
CREATE_INVITES     = 1 << 31
CHANGE_NICKNAME    = 1 << 32
MANAGE_NICKNAMES   = 1 << 33
VIEW_AUDIT_LOG     = 1 << 34
MANAGE_MESSAGES    = 1 << 35
VIEW_REPORTS       = 1 << 36
MANAGE_2FA         = 1 << 37
MANAGE_REPORTS     = 1 << 38
ADMINISTRATOR      = 1 << 62

ALL_PERMISSIONS = (1 << 63) - 1

# Default permissions for the @everyone base role (position=0).
EVERYONE_DEFAULTS = (
    VIEW_SPACE | SEND_MESSAGES | READ_HISTORY | ADD_REACTIONS
    | CONNECT | SPEAK | CREATE_INVITES | CHANGE_NICKNAME
    | CREATE_THREADS | SEND_IN_THREADS
)


async def resolve_permissions(
    db: AsyncSession,
    user_id: int,
    *,
    space_type: str | None = None,
    space_id: int | None = None,
) -> int:
    """Resolve effective permissions for *user_id*, optionally scoped to a space."""

    # 1. Fetch @everyone base role (position=0, name='@everyone')
    everyone_result = await db.execute(
        select(Role).where(Role.position == 0, Role.name == "@everyone")
    )
    everyone_role = everyone_result.scalar_one_or_none()
    base = everyone_role.permissions if everyone_role else 0

    # 2. Fetch user's explicit roles (via role_members junction)
    user_role_ids_result = await db.execute(
        select(role_members.c.role_id).where(role_members.c.user_id == user_id)
    )
    user_role_ids = set(user_role_ids_result.scalars().all())

    if user_role_ids:
        roles_result = await db.execute(
            select(Role).where(Role.id.in_(user_role_ids), Role.position != 0)
        )
        for role in roles_result.scalars().all():
            base |= role.permissions

    # 3. Early admin short-circuit (before overrides – admin overrides everything)
    if base & ADMINISTRATOR:
        return ALL_PERMISSIONS

    # 4. Apply space-scoped permission overrides
    if space_type and space_id is not None:
        overrides_result = await db.execute(
            select(PermissionOverride).where(
                PermissionOverride.space_type == space_type,
                PermissionOverride.space_id == space_id,
            )
        )
        overrides = overrides_result.scalars().all()

        everyone_role_id = everyone_role.id if everyone_role else None

        # 5a. @everyone role override
        for o in overrides:
            if o.target_type == "role" and o.target_id == everyone_role_id:
                base = (base & ~o.deny) | o.allow

        # 5b. User's role overrides (union all allow, union all deny, then apply)
        role_allow = 0
        role_deny = 0
        for o in overrides:
            if o.target_type == "role" and o.target_id in user_role_ids:
                role_allow |= o.allow
                role_deny |= o.deny
        base = (base & ~role_deny) | role_allow

        # 5c. User-specific override
        for o in overrides:
            if o.target_type == "user" and o.target_id == user_id:
                base = (base & ~o.deny) | o.allow

    # Re-check admin after overrides
    if base & ADMINISTRATOR:
        return ALL_PERMISSIONS

    return base


def has_permission(resolved: int, required: int) -> bool:
    """Return True if *resolved* contains all bits in *required*."""
    return (resolved & required) == required


async def batch_resolve_permissions(
    db: AsyncSession,
    user_ids: list[int],
    *,
    space_type: str | None = None,
    space_id: int | None = None,
) -> dict[int, int]:
    """Resolve effective permissions for multiple users in bulk.

    Returns a dict mapping user_id -> resolved permission bitfield.
    """
    from vox.db.models import User

    # 1. Fetch @everyone base role
    everyone_result = await db.execute(
        select(Role).where(Role.position == 0, Role.name == "@everyone")
    )
    everyone_role = everyone_result.scalar_one_or_none()
    everyone_perms = everyone_role.permissions if everyone_role else 0
    everyone_role_id = everyone_role.id if everyone_role else None

    # 2. Fetch all role assignments for these users
    rm_result = await db.execute(
        select(role_members.c.user_id, role_members.c.role_id)
        .where(role_members.c.user_id.in_(user_ids))
    )
    user_role_map: dict[int, set[int]] = {uid: set() for uid in user_ids}
    for uid, rid in rm_result.all():
        user_role_map[uid].add(rid)

    # 3. Fetch all roles referenced
    all_role_ids = set()
    for rids in user_role_map.values():
        all_role_ids |= rids
    role_perms: dict[int, int] = {}
    if all_role_ids:
        roles_result = await db.execute(
            select(Role).where(Role.id.in_(all_role_ids), Role.position != 0)
        )
        for role in roles_result.scalars().all():
            role_perms[role.id] = role.permissions

    # 4. Fetch space overrides (once)
    overrides = []
    if space_type and space_id is not None:
        ov_result = await db.execute(
            select(PermissionOverride).where(
                PermissionOverride.space_type == space_type,
                PermissionOverride.space_id == space_id,
            )
        )
        overrides = ov_result.scalars().all()

    # 5. Compute per-user permissions
    results: dict[int, int] = {}
    for uid in user_ids:
        base = everyone_perms
        for rid in user_role_map[uid]:
            base |= role_perms.get(rid, 0)

        if base & ADMINISTRATOR:
            results[uid] = ALL_PERMISSIONS
            continue

        if overrides:
            # @everyone role override
            for o in overrides:
                if o.target_type == "role" and o.target_id == everyone_role_id:
                    base = (base & ~o.deny) | o.allow

            # User's role overrides
            role_allow = 0
            role_deny = 0
            for o in overrides:
                if o.target_type == "role" and o.target_id in user_role_map[uid]:
                    role_allow |= o.allow
                    role_deny |= o.deny
            base = (base & ~role_deny) | role_allow

            # User-specific override
            for o in overrides:
                if o.target_type == "user" and o.target_id == uid:
                    base = (base & ~o.deny) | o.allow

        if base & ADMINISTRATOR:
            results[uid] = ALL_PERMISSIONS
        else:
            results[uid] = base

    return results

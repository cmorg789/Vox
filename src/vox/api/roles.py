from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.api.members import get_highest_role_position
from vox.db.models import PermissionOverride, Role, User, role_members
from vox.limits import limits
from vox.permissions import ADMINISTRATOR, MANAGE_ROLES, VIEW_SPACE, has_permission, resolve_permissions
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.roles import (
    CreateRoleRequest,
    PermissionOverrideRequest,
    RoleResponse,
    UpdateRoleRequest,
)

router = APIRouter(tags=["roles"])


async def _get_space_viewers(db: AsyncSession, space_type: str, space_id: int) -> list[int]:
    """Get user IDs who have VIEW_SPACE permission for a feed/room."""
    result = await db.execute(select(User.id).where(User.active == True))
    all_user_ids = result.scalars().all()
    viewers = []
    for uid in all_user_ids:
        resolved = await resolve_permissions(db, uid, space_type=space_type, space_id=space_id)
        if has_permission(resolved, VIEW_SPACE):
            viewers.append(uid)
    return viewers


# --- Roles ---

@router.get("/api/v1/roles")
async def list_roles(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    limit = min(limit, limits.page_limit_roles)
    query = select(Role).order_by(Role.id).limit(limit)
    if after is not None:
        query = query.where(Role.id > after)
    result = await db.execute(query)
    roles = result.scalars().all()
    items = [RoleResponse(role_id=r.id, name=r.name, color=r.color, permissions=r.permissions, position=r.position) for r in roles]
    cursor = str(roles[-1].id) if roles else None
    return {"items": items, "cursor": cursor}


@router.get("/api/v1/roles/{role_id}/members")
async def list_role_members(
    role_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from vox.models.members import MemberListResponse, MemberResponse
    from vox.auth.service import get_user_role_ids
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Role not found."}})
    limit = min(limit, limits.page_limit_members)
    query = (
        select(User)
        .join(role_members, role_members.c.user_id == User.id)
        .where(role_members.c.role_id == role_id)
        .order_by(User.id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(User.id > after)
    result = await db.execute(query)
    users = result.scalars().all()
    items = []
    for u in users:
        rids = await get_user_role_ids(db, u.id)
        items.append(MemberResponse(user_id=u.id, display_name=u.display_name, avatar=u.avatar, nickname=u.nickname, role_ids=rids))
    cursor = str(users[-1].id) if users else None
    return MemberListResponse(items=items, cursor=cursor)


@router.post("/api/v1/roles", status_code=201)
async def create_role(
    body: CreateRoleRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_ROLES),
) -> RoleResponse:
    role = Role(name=body.name, color=body.color, permissions=body.permissions, position=body.position)
    db.add(role)
    await db.flush()
    from vox.audit import write_audit
    await write_audit(db, "role.create", actor_id=actor.id, target_id=role.id)
    await db.commit()
    await dispatch(gw.role_create(role_id=role.id, name=role.name, color=role.color, permissions=role.permissions, position=role.position))
    return RoleResponse(role_id=role.id, name=role.name, color=role.color, permissions=role.permissions, position=role.position)


@router.patch("/api/v1/roles/{role_id}")
async def update_role(
    role_id: int,
    body: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_ROLES),
) -> RoleResponse:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Role not found."}})
    # Administrators bypass hierarchy; others cannot edit roles at or above their rank
    resolved = await resolve_permissions(db, actor.id)
    if not has_permission(resolved, ADMINISTRATOR):
        actor_pos = await get_highest_role_position(db, actor.id)
        if role.position <= actor_pos:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "ROLE_HIERARCHY", "message": "You cannot edit a role at or above your own rank."}},
            )
    changed = {}
    if body.name is not None:
        role.name = body.name
        changed["name"] = body.name
    if body.color is not None:
        role.color = body.color
        changed["color"] = body.color
    if body.permissions is not None:
        role.permissions = body.permissions
        changed["permissions"] = body.permissions
    if body.position is not None:
        role.position = body.position
        changed["position"] = body.position
    await db.commit()
    if changed:
        await dispatch(gw.role_update(role_id=role_id, **changed))
    return RoleResponse(role_id=role.id, name=role.name, color=role.color, permissions=role.permissions, position=role.position)


@router.delete("/api/v1/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_ROLES),
):
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Role not found."}})
    from vox.audit import write_audit
    await write_audit(db, "role.delete", actor_id=actor.id, target_id=role_id)
    await db.delete(role)
    await db.commit()
    await dispatch(gw.role_delete(role_id=role_id))


@router.put("/api/v1/members/{user_id}/roles/{role_id}", status_code=204)
async def assign_role(
    user_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_ROLES),
):
    # Administrators bypass hierarchy; others cannot assign roles at or above their rank
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Role not found."}})
    resolved = await resolve_permissions(db, actor.id)
    if not has_permission(resolved, ADMINISTRATOR):
        actor_pos = await get_highest_role_position(db, actor.id)
        if role.position <= actor_pos:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "ROLE_HIERARCHY", "message": "You cannot assign a role at or above your own rank."}},
            )
    await db.execute(sqlite_insert(role_members).values(role_id=role_id, user_id=user_id).on_conflict_do_nothing())
    from vox.audit import write_audit
    await write_audit(db, "role.assign", actor_id=actor.id, target_id=user_id)
    await db.commit()
    await dispatch(gw.role_assign(role_id=role_id, user_id=user_id))


@router.delete("/api/v1/members/{user_id}/roles/{role_id}", status_code=204)
async def revoke_role(
    user_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_ROLES),
):
    # Administrators bypass hierarchy; others cannot revoke roles at or above their rank
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Role not found."}})
    resolved = await resolve_permissions(db, actor.id)
    if not has_permission(resolved, ADMINISTRATOR):
        actor_pos = await get_highest_role_position(db, actor.id)
        if role.position <= actor_pos:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "ROLE_HIERARCHY", "message": "You cannot revoke a role at or above your own rank."}},
            )
    await db.execute(delete(role_members).where(role_members.c.role_id == role_id, role_members.c.user_id == user_id))
    from vox.audit import write_audit
    await write_audit(db, "role.revoke", actor_id=actor.id, target_id=user_id)
    await db.commit()
    await dispatch(gw.role_revoke(role_id=role_id, user_id=user_id))


# --- Permission Overrides ---

@router.put("/api/v1/feeds/{feed_id}/permissions/{target_type}/{target_id}", status_code=204)
async def set_feed_permission_override(
    feed_id: int,
    target_type: str,
    target_id: int,
    body: PermissionOverrideRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
):
    result = await db.execute(
        select(PermissionOverride).where(
            PermissionOverride.space_type == "feed",
            PermissionOverride.space_id == feed_id,
            PermissionOverride.target_type == target_type,
            PermissionOverride.target_id == target_id,
        )
    )
    override = result.scalar_one_or_none()
    if override:
        override.allow = body.allow
        override.deny = body.deny
    else:
        db.add(PermissionOverride(space_type="feed", space_id=feed_id, target_type=target_type, target_id=target_id, allow=body.allow, deny=body.deny))
    await db.commit()
    viewers = await _get_space_viewers(db, "feed", feed_id)
    await dispatch(gw.permission_override_update(space_type="feed", space_id=feed_id, target_type=target_type, target_id=target_id, allow=body.allow, deny=body.deny), user_ids=viewers)


@router.delete("/api/v1/feeds/{feed_id}/permissions/{target_type}/{target_id}", status_code=204)
async def delete_feed_permission_override(
    feed_id: int,
    target_type: str,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
):
    await db.execute(
        delete(PermissionOverride).where(
            PermissionOverride.space_type == "feed",
            PermissionOverride.space_id == feed_id,
            PermissionOverride.target_type == target_type,
            PermissionOverride.target_id == target_id,
        )
    )
    await db.commit()
    viewers = await _get_space_viewers(db, "feed", feed_id)
    await dispatch(gw.permission_override_delete(space_type="feed", space_id=feed_id, target_type=target_type, target_id=target_id), user_ids=viewers)


@router.put("/api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}", status_code=204)
async def set_room_permission_override(
    room_id: int,
    target_type: str,
    target_id: int,
    body: PermissionOverrideRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
):
    result = await db.execute(
        select(PermissionOverride).where(
            PermissionOverride.space_type == "room",
            PermissionOverride.space_id == room_id,
            PermissionOverride.target_type == target_type,
            PermissionOverride.target_id == target_id,
        )
    )
    override = result.scalar_one_or_none()
    if override:
        override.allow = body.allow
        override.deny = body.deny
    else:
        db.add(PermissionOverride(space_type="room", space_id=room_id, target_type=target_type, target_id=target_id, allow=body.allow, deny=body.deny))
    await db.commit()
    viewers = await _get_space_viewers(db, "room", room_id)
    await dispatch(gw.permission_override_update(space_type="room", space_id=room_id, target_type=target_type, target_id=target_id, allow=body.allow, deny=body.deny), user_ids=viewers)


@router.delete("/api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}", status_code=204)
async def delete_room_permission_override(
    room_id: int,
    target_type: str,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
):
    await db.execute(
        delete(PermissionOverride).where(
            PermissionOverride.space_type == "room",
            PermissionOverride.space_id == room_id,
            PermissionOverride.target_type == target_type,
            PermissionOverride.target_id == target_id,
        )
    )
    await db.commit()
    viewers = await _get_space_viewers(db, "room", room_id)
    await dispatch(gw.permission_override_delete(space_type="room", space_id=room_id, target_type=target_type, target_id=target_id), user_ids=viewers)

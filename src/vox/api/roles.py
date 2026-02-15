from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import PermissionOverride, Role, User, role_members
from vox.permissions import MANAGE_ROLES
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.roles import (
    CreateRoleRequest,
    PermissionOverrideRequest,
    RoleResponse,
    UpdateRoleRequest,
)

router = APIRouter(tags=["roles"])


# --- Roles ---

@router.get("/api/v1/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Role).order_by(Role.position))
    roles = result.scalars().all()
    return {"roles": [RoleResponse(role_id=r.id, name=r.name, color=r.color, permissions=r.permissions, position=r.position) for r in roles]}


@router.post("/api/v1/roles", status_code=201)
async def create_role(
    body: CreateRoleRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
) -> RoleResponse:
    role = Role(name=body.name, color=body.color, permissions=body.permissions, position=body.position)
    db.add(role)
    await db.flush()
    await db.commit()
    await dispatch(gw.role_create(role_id=role.id, name=role.name, color=role.color, permissions=role.permissions, position=role.position))
    return RoleResponse(role_id=role.id, name=role.name, color=role.color, permissions=role.permissions, position=role.position)


@router.patch("/api/v1/roles/{role_id}")
async def update_role(
    role_id: int,
    body: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
) -> RoleResponse:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Role not found."}})
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
    _: User = require_permission(MANAGE_ROLES),
):
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Role not found."}})
    await db.delete(role)
    await db.commit()
    await dispatch(gw.role_delete(role_id=role_id))


@router.put("/api/v1/members/{user_id}/roles/{role_id}", status_code=204)
async def assign_role(
    user_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
):
    await db.execute(role_members.insert().values(role_id=role_id, user_id=user_id))
    await db.commit()


@router.delete("/api/v1/members/{user_id}/roles/{role_id}", status_code=204)
async def revoke_role(
    user_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_ROLES),
):
    await db.execute(delete(role_members).where(role_members.c.role_id == role_id, role_members.c.user_id == user_id))
    await db.commit()


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


@router.delete("/api/v1/feeds/{feed_id}/permissions/{target_type}/{target_id}", status_code=204)
async def delete_feed_permission_override(
    feed_id: int,
    target_type: str,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
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


@router.put("/api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}", status_code=204)
async def set_room_permission_override(
    room_id: int,
    target_type: str,
    target_id: int,
    body: PermissionOverrideRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
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


@router.delete("/api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}", status_code=204)
async def delete_room_permission_override(
    room_id: int,
    target_type: str,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
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

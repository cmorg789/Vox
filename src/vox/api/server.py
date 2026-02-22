from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Category, Feed, PermissionOverride, Room, User
from vox.config import config, save_config_value, save_limit
from vox.permissions import MANAGE_SERVER
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.server import (
    CategoryInfo,
    FeedInfo,
    PermissionOverrideData,
    RoomInfo,
    ServerInfoResponse,
    ServerLayoutResponse,
    UpdateServerRequest,
)

router = APIRouter(prefix="/api/v1/server", tags=["server"])


@router.get("")
async def get_server_info(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ServerInfoResponse:
    result = await db.execute(select(func.count()).select_from(User).where(User.federated == False, User.active == True))
    member_count = result.scalar() or 0
    return ServerInfoResponse(
        name=config.server.name,
        icon=config.server.icon,
        description=config.server.description,
        member_count=member_count,
    )


@router.patch("")
async def update_server(
    body: UpdateServerRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SERVER),
):
    changed = {}
    if body.name is not None:
        await save_config_value(db, "server_name", body.name)
        changed["name"] = body.name
    if body.icon is not None:
        await save_config_value(db, "server_icon", body.icon)
        changed["icon"] = body.icon
    if body.description is not None:
        await save_config_value(db, "server_description", body.description)
        changed["description"] = body.description
    from vox.audit import write_audit
    await write_audit(db, "server.update", actor_id=actor.id, extra=changed if changed else None)
    await db.commit()
    if changed:
        await dispatch(gw.server_update(**changed), db=db)
    return await get_server_info(db=db, _=actor)


async def _overrides_for(db: AsyncSession, space_type: str, space_id: int) -> list[PermissionOverrideData]:
    result = await db.execute(
        select(PermissionOverride).where(
            PermissionOverride.space_type == space_type,
            PermissionOverride.space_id == space_id,
        )
    )
    return [
        PermissionOverrideData(target_type=o.target_type, target_id=o.target_id, allow=o.allow, deny=o.deny)
        for o in result.scalars().all()
    ]


@router.get("/layout")
async def get_layout(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ServerLayoutResponse:
    cats = (await db.execute(select(Category).order_by(Category.position))).scalars().all()
    feed_rows = (await db.execute(select(Feed).order_by(Feed.position))).scalars().all()
    room_rows = (await db.execute(select(Room).order_by(Room.position))).scalars().all()

    feeds = []
    for f in feed_rows:
        overrides = await _overrides_for(db, "feed", f.id)
        feeds.append(FeedInfo(feed_id=f.id, name=f.name, type=f.type, topic=f.topic, category_id=f.category_id, position=f.position, permission_overrides=overrides))

    rooms = []
    for r in room_rows:
        overrides = await _overrides_for(db, "room", r.id)
        rooms.append(RoomInfo(room_id=r.id, name=r.name, type=r.type, category_id=r.category_id, position=r.position, permission_overrides=overrides))

    categories = [CategoryInfo(category_id=c.id, name=c.name, position=c.position) for c in cats]
    return ServerLayoutResponse(categories=categories, feeds=feeds, rooms=rooms)


# --- Limits ---


class UpdateLimitsRequest(BaseModel):
    limits: dict[str, int]


from vox.config import LimitsConfig


@router.get("/limits", response_model=LimitsConfig)
async def get_limits(
    _: User = require_permission(MANAGE_SERVER),
):
    """Returns all limits with current (effective) values."""
    return config.limits


@router.patch("/limits", response_model=LimitsConfig)
async def update_limits(
    body: UpdateLimitsRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_SERVER),
):
    """Update specific limits. Writes to DB and hot-reloads in-memory."""
    valid_fields = set(type(config.limits).model_fields)
    for name, value in body.limits.items():
        if name not in valid_fields:
            raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_LIMIT", "message": f"Unknown limit: {name}"}})
        await save_limit(db, name, value)
    await db.commit()
    return config.limits

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Category, Config, Feed, PermissionOverride, Room, User
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


async def _get_config(db: AsyncSession, key: str) -> str | None:
    result = await db.execute(select(Config).where(Config.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _set_config(db: AsyncSession, key: str, value: str):
    existing = await db.execute(select(Config).where(Config.key == key))
    row = existing.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(Config(key=key, value=value))


@router.get("")
async def get_server_info(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ServerInfoResponse:
    name = await _get_config(db, "server_name") or "Vox Server"
    icon = await _get_config(db, "server_icon")
    description = await _get_config(db, "server_description")
    result = await db.execute(select(func.count()).select_from(User).where(User.federated == False, User.active == True))
    member_count = result.scalar() or 0
    return ServerInfoResponse(name=name, icon=icon, description=description, member_count=member_count)


@router.patch("")
async def update_server(
    body: UpdateServerRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_SERVER),
):
    changed = {}
    if body.name is not None:
        await _set_config(db, "server_name", body.name)
        changed["name"] = body.name
    if body.icon is not None:
        await _set_config(db, "server_icon", body.icon)
        changed["icon"] = body.icon
    if body.description is not None:
        await _set_config(db, "server_description", body.description)
        changed["description"] = body.description
    await db.commit()
    if changed:
        await dispatch(gw.server_update(**changed))
    return await get_server_info(db=db, _=_)


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
        feeds.append(FeedInfo(feed_id=f.id, name=f.name, type=f.type, topic=f.topic, category_id=f.category_id, permission_overrides=overrides))

    rooms = []
    for r in room_rows:
        overrides = await _overrides_for(db, "room", r.id)
        rooms.append(RoomInfo(room_id=r.id, name=r.name, type=r.type, category_id=r.category_id, permission_overrides=overrides))

    categories = [CategoryInfo(category_id=c.id, name=c.name, position=c.position) for c in cats]
    return ServerLayoutResponse(categories=categories, feeds=feeds, rooms=rooms)

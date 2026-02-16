from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Category, Feed, PermissionOverride, Room, Thread, User, feed_subscribers, thread_subscribers
from vox.permissions import CREATE_THREADS, MANAGE_SPACES, MANAGE_THREADS
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.server import PermissionOverrideData
from vox.models.channels import (
    CategoryResponse,
    CreateCategoryRequest,
    CreateFeedRequest,
    CreateRoomRequest,
    CreateThreadRequest,
    FeedResponse,
    RoomResponse,
    ThreadResponse,
    UpdateCategoryRequest,
    UpdateFeedRequest,
    UpdateRoomRequest,
    UpdateThreadRequest,
)

router = APIRouter(tags=["channels"])


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


# --- Feeds ---

@router.get("/api/v1/feeds/{feed_id}")
async def get_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FeedResponse:
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Feed does not exist."}})
    overrides = await _overrides_for(db, "feed", feed.id)
    return FeedResponse(feed_id=feed.id, name=feed.name, type=feed.type, topic=feed.topic, category_id=feed.category_id, permission_overrides=overrides)


@router.post("/api/v1/feeds", status_code=201)
async def create_feed(
    body: CreateFeedRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
) -> FeedResponse:
    max_pos = (await db.execute(select(Feed.position).order_by(Feed.position.desc()).limit(1))).scalar() or 0
    feed = Feed(name=body.name, type=body.type, category_id=body.category_id, position=max_pos + 1)
    db.add(feed)
    await db.flush()
    from vox.audit import write_audit
    await write_audit(db, "feed.create", actor_id=actor.id, target_id=feed.id)
    await db.commit()
    await dispatch(gw.feed_create(feed_id=feed.id, name=feed.name, type=feed.type, category_id=feed.category_id))
    overrides = await _overrides_for(db, "feed", feed.id)
    return FeedResponse(feed_id=feed.id, name=feed.name, type=feed.type, topic=feed.topic, category_id=feed.category_id, permission_overrides=overrides)


@router.patch("/api/v1/feeds/{feed_id}")
async def update_feed(
    feed_id: int,
    body: UpdateFeedRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_SPACES),
) -> FeedResponse:
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Feed does not exist."}})
    changed = {}
    if body.name is not None:
        feed.name = body.name
        changed["name"] = body.name
    if body.topic is not None:
        feed.topic = body.topic
        changed["topic"] = body.topic
    await db.commit()
    if changed:
        await dispatch(gw.feed_update(feed_id=feed_id, **changed))
    overrides = await _overrides_for(db, "feed", feed.id)
    return FeedResponse(feed_id=feed.id, name=feed.name, type=feed.type, topic=feed.topic, category_id=feed.category_id, permission_overrides=overrides)


@router.delete("/api/v1/feeds/{feed_id}", status_code=204)
async def delete_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
):
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Feed does not exist."}})
    from vox.audit import write_audit
    await write_audit(db, "feed.delete", actor_id=actor.id, target_id=feed_id)
    await db.delete(feed)
    await db.commit()
    await dispatch(gw.feed_delete(feed_id=feed_id))


# --- Rooms ---

@router.post("/api/v1/rooms", status_code=201)
async def create_room(
    body: CreateRoomRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
) -> RoomResponse:
    max_pos = (await db.execute(select(Room.position).order_by(Room.position.desc()).limit(1))).scalar() or 0
    room = Room(name=body.name, type=body.type, category_id=body.category_id, position=max_pos + 1)
    db.add(room)
    await db.flush()
    from vox.audit import write_audit
    await write_audit(db, "room.create", actor_id=actor.id, target_id=room.id)
    await db.commit()
    await dispatch(gw.room_create(room_id=room.id, name=room.name, type=room.type, category_id=room.category_id))
    overrides = await _overrides_for(db, "room", room.id)
    return RoomResponse(room_id=room.id, name=room.name, type=room.type, category_id=room.category_id, permission_overrides=overrides)


@router.patch("/api/v1/rooms/{room_id}")
async def update_room(
    room_id: int,
    body: UpdateRoomRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_SPACES),
) -> RoomResponse:
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Room does not exist."}})
    changed = {}
    if body.name is not None:
        room.name = body.name
        changed["name"] = body.name
    await db.commit()
    if changed:
        await dispatch(gw.room_update(room_id=room_id, **changed))
    overrides = await _overrides_for(db, "room", room.id)
    return RoomResponse(room_id=room.id, name=room.name, type=room.type, category_id=room.category_id, permission_overrides=overrides)


@router.delete("/api/v1/rooms/{room_id}", status_code=204)
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Room does not exist."}})
    from vox.audit import write_audit
    await write_audit(db, "room.delete", actor_id=actor.id, target_id=room_id)
    await db.delete(room)
    await db.commit()
    await dispatch(gw.room_delete(room_id=room_id))


# --- Categories ---

@router.post("/api/v1/categories", status_code=201)
async def create_category(
    body: CreateCategoryRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_SPACES),
) -> CategoryResponse:
    cat = Category(name=body.name, position=body.position)
    db.add(cat)
    await db.flush()
    await db.commit()
    await dispatch(gw.category_create(category_id=cat.id, name=cat.name, position=cat.position))
    return CategoryResponse(category_id=cat.id, name=cat.name, position=cat.position)


@router.patch("/api/v1/categories/{category_id}")
async def update_category(
    category_id: int,
    body: UpdateCategoryRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_SPACES),
) -> CategoryResponse:
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Category does not exist."}})
    changed = {}
    if body.name is not None:
        cat.name = body.name
        changed["name"] = body.name
    if body.position is not None:
        cat.position = body.position
        changed["position"] = body.position
    await db.commit()
    if changed:
        await dispatch(gw.category_update(category_id=category_id, **changed))
    return CategoryResponse(category_id=cat.id, name=cat.name, position=cat.position)


@router.delete("/api/v1/categories/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_SPACES),
):
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Category does not exist."}})
    await db.delete(cat)
    await db.commit()
    await dispatch(gw.category_delete(category_id=category_id))


# --- Threads ---

@router.post("/api/v1/feeds/{feed_id}/threads", status_code=201)
async def create_thread(
    feed_id: int,
    body: CreateThreadRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(CREATE_THREADS, space_type="feed", space_id_param="feed_id"),
) -> ThreadResponse:
    thread = Thread(name=body.name, feed_id=feed_id, parent_msg_id=body.parent_msg_id)
    db.add(thread)
    await db.flush()
    await db.commit()
    await dispatch(gw.thread_create(thread_id=thread.id, parent_feed_id=feed_id, name=thread.name, parent_msg_id=thread.parent_msg_id))
    return ThreadResponse(thread_id=thread.id, parent_feed_id=feed_id, parent_msg_id=thread.parent_msg_id, name=thread.name, archived=thread.archived, locked=thread.locked)


@router.patch("/api/v1/threads/{thread_id}")
async def update_thread(
    thread_id: int,
    body: UpdateThreadRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_THREADS),
) -> ThreadResponse:
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist."}})
    changed = {}
    if body.name is not None:
        thread.name = body.name
        changed["name"] = body.name
    if body.archived is not None:
        thread.archived = body.archived
        changed["archived"] = body.archived
    if body.locked is not None:
        thread.locked = body.locked
        changed["locked"] = body.locked
    await db.commit()
    if changed:
        await dispatch(gw.thread_update(thread_id=thread_id, **changed))
    return ThreadResponse(thread_id=thread.id, parent_feed_id=thread.feed_id, parent_msg_id=thread.parent_msg_id, name=thread.name, archived=thread.archived, locked=thread.locked)


@router.delete("/api/v1/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_THREADS),
):
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist."}})
    await db.delete(thread)
    await db.commit()
    await dispatch(gw.thread_delete(thread_id=thread_id))


@router.put("/api/v1/threads/{thread_id}/subscribers/@me", status_code=204)
async def subscribe_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(sqlite_insert(thread_subscribers).values(thread_id=thread_id, user_id=user.id).on_conflict_do_nothing())
    await db.commit()


@router.delete("/api/v1/threads/{thread_id}/subscribers/@me", status_code=204)
async def unsubscribe_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from sqlalchemy import delete
    await db.execute(delete(thread_subscribers).where(thread_subscribers.c.thread_id == thread_id, thread_subscribers.c.user_id == user.id))
    await db.commit()

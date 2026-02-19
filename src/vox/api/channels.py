from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete

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
    return FeedResponse(feed_id=feed.id, name=feed.name, type=feed.type, topic=feed.topic, category_id=feed.category_id, position=feed.position, permission_overrides=overrides)


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
    if body.permission_overrides:
        for o in body.permission_overrides:
            db.add(PermissionOverride(space_type="feed", space_id=feed.id, target_type=o.target_type, target_id=o.target_id, allow=o.allow, deny=o.deny))
    from vox.audit import write_audit
    await write_audit(db, "feed.create", actor_id=actor.id, target_id=feed.id)
    await db.commit()
    await dispatch(gw.feed_create(feed_id=feed.id, name=feed.name, type=feed.type, category_id=feed.category_id), db=db)
    overrides = await _overrides_for(db, "feed", feed.id)
    return FeedResponse(feed_id=feed.id, name=feed.name, type=feed.type, topic=feed.topic, category_id=feed.category_id, position=feed.position, permission_overrides=overrides)


@router.patch("/api/v1/feeds/{feed_id}")
async def update_feed(
    feed_id: int,
    body: UpdateFeedRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
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
    from vox.audit import write_audit
    await write_audit(db, "feed.update", actor_id=actor.id, target_id=feed_id, extra=changed if changed else None)
    await db.commit()
    if changed:
        await dispatch(gw.feed_update(feed_id=feed_id, **changed), db=db)
    overrides = await _overrides_for(db, "feed", feed.id)
    return FeedResponse(feed_id=feed.id, name=feed.name, type=feed.type, topic=feed.topic, category_id=feed.category_id, position=feed.position, permission_overrides=overrides)


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
    await dispatch(gw.feed_delete(feed_id=feed_id), db=db)


# --- Feed Subscriptions ---

@router.put("/api/v1/feeds/{feed_id}/subscribers", status_code=204)
async def subscribe_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Feed does not exist."}})
    await db.execute(sqlite_insert(feed_subscribers).values(feed_id=feed_id, user_id=user.id).on_conflict_do_nothing())
    await db.commit()
    await dispatch(gw.feed_subscribe(feed_id=feed_id, user_id=user.id), db=db)


@router.delete("/api/v1/feeds/{feed_id}/subscribers", status_code=204)
async def unsubscribe_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Feed does not exist."}})
    await db.execute(delete(feed_subscribers).where(feed_subscribers.c.feed_id == feed_id, feed_subscribers.c.user_id == user.id))
    await db.commit()
    await dispatch(gw.feed_unsubscribe(feed_id=feed_id, user_id=user.id), db=db)


# --- Rooms ---

@router.get("/api/v1/rooms/{room_id}")
async def get_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> RoomResponse:
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Room does not exist."}})
    overrides = await _overrides_for(db, "room", room.id)
    return RoomResponse(room_id=room.id, name=room.name, type=room.type, category_id=room.category_id, position=room.position, permission_overrides=overrides)


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
    if body.permission_overrides:
        for o in body.permission_overrides:
            db.add(PermissionOverride(space_type="room", space_id=room.id, target_type=o.target_type, target_id=o.target_id, allow=o.allow, deny=o.deny))
    from vox.audit import write_audit
    await write_audit(db, "room.create", actor_id=actor.id, target_id=room.id)
    await db.commit()
    await dispatch(gw.room_create(room_id=room.id, name=room.name, type=room.type, category_id=room.category_id), db=db)
    overrides = await _overrides_for(db, "room", room.id)
    return RoomResponse(room_id=room.id, name=room.name, type=room.type, category_id=room.category_id, position=room.position, permission_overrides=overrides)


@router.patch("/api/v1/rooms/{room_id}")
async def update_room(
    room_id: int,
    body: UpdateRoomRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
) -> RoomResponse:
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Room does not exist."}})
    changed = {}
    if body.name is not None:
        room.name = body.name
        changed["name"] = body.name
    from vox.audit import write_audit
    await write_audit(db, "room.update", actor_id=actor.id, target_id=room_id, extra=changed if changed else None)
    await db.commit()
    if changed:
        await dispatch(gw.room_update(room_id=room_id, **changed), db=db)
    overrides = await _overrides_for(db, "room", room.id)
    return RoomResponse(room_id=room.id, name=room.name, type=room.type, category_id=room.category_id, position=room.position, permission_overrides=overrides)


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
    await dispatch(gw.room_delete(room_id=room_id), db=db)


# --- Categories ---

@router.post("/api/v1/categories", status_code=201)
async def create_category(
    body: CreateCategoryRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
) -> CategoryResponse:
    cat = Category(name=body.name, position=body.position)
    db.add(cat)
    await db.flush()
    from vox.audit import write_audit
    await write_audit(db, "category.create", actor_id=actor.id, target_id=cat.id)
    await db.commit()
    await dispatch(gw.category_create(category_id=cat.id, name=cat.name, position=cat.position), db=db)
    return CategoryResponse(category_id=cat.id, name=cat.name, position=cat.position)


@router.patch("/api/v1/categories/{category_id}")
async def update_category(
    category_id: int,
    body: UpdateCategoryRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_SPACES),
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
    from vox.audit import write_audit
    await write_audit(db, "category.update", actor_id=actor.id, target_id=category_id, extra=changed if changed else None)
    await db.commit()
    if changed:
        await dispatch(gw.category_update(category_id=category_id, **changed), db=db)
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
    await dispatch(gw.category_delete(category_id=category_id), db=db)


# --- Threads ---

@router.get("/api/v1/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Category).order_by(Category.position))
    cats = result.scalars().all()
    return {"items": [CategoryResponse(category_id=c.id, name=c.name, position=c.position) for c in cats]}


@router.get("/api/v1/categories/{category_id}")
async def get_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CategoryResponse:
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Category does not exist."}})
    return CategoryResponse(category_id=cat.id, name=cat.name, position=cat.position)


@router.get("/api/v1/threads/{thread_id}")
async def get_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ThreadResponse:
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist."}})
    return ThreadResponse(thread_id=thread.id, parent_feed_id=thread.feed_id, parent_msg_id=thread.parent_msg_id, name=thread.name, archived=thread.archived, locked=thread.locked)


@router.get("/api/v1/feeds/{feed_id}/threads")
async def list_feed_threads(
    feed_id: int,
    limit: int = 50,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from vox.config import limits
    limit = min(limit, limits.page_limit_messages)
    query = select(Thread).where(Thread.feed_id == feed_id).order_by(Thread.id).limit(limit)
    if after is not None:
        query = query.where(Thread.id > after)
    result = await db.execute(query)
    threads = result.scalars().all()
    items = [ThreadResponse(thread_id=t.id, parent_feed_id=t.feed_id, parent_msg_id=t.parent_msg_id, name=t.name, archived=t.archived, locked=t.locked) for t in threads]
    cursor = str(threads[-1].id) if threads else None
    return {"items": items, "cursor": cursor}


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
    await dispatch(gw.thread_create(thread_id=thread.id, parent_feed_id=feed_id, name=thread.name, parent_msg_id=thread.parent_msg_id), db=db)
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
        await dispatch(gw.thread_update(thread_id=thread_id, **changed), db=db)
    return ThreadResponse(thread_id=thread.id, parent_feed_id=thread.feed_id, parent_msg_id=thread.parent_msg_id, name=thread.name, archived=thread.archived, locked=thread.locked)


@router.delete("/api/v1/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(MANAGE_THREADS),
):
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist."}})
    from vox.audit import write_audit
    await write_audit(db, "thread.delete", actor_id=actor.id, target_id=thread_id)
    await db.delete(thread)
    await db.commit()
    await dispatch(gw.thread_delete(thread_id=thread_id), db=db)


@router.put("/api/v1/feeds/{feed_id}/threads/{thread_id}/subscribers", status_code=204)
async def subscribe_thread(
    feed_id: int,
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = (await db.execute(select(Thread).where(Thread.id == thread_id))).scalar_one_or_none()
    if thread is None or thread.feed_id != feed_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist in this feed."}})
    await db.execute(sqlite_insert(thread_subscribers).values(thread_id=thread_id, user_id=user.id).on_conflict_do_nothing())
    await db.commit()
    await dispatch(gw.thread_subscribe(thread_id=thread_id, user_id=user.id), db=db)


@router.delete("/api/v1/feeds/{feed_id}/threads/{thread_id}/subscribers", status_code=204)
async def unsubscribe_thread(
    feed_id: int,
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = (await db.execute(select(Thread).where(Thread.id == thread_id))).scalar_one_or_none()
    if thread is None or thread.feed_id != feed_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist in this feed."}})
    await db.execute(delete(thread_subscribers).where(thread_subscribers.c.thread_id == thread_id, thread_subscribers.c.user_id == user.id))
    await db.commit()
    await dispatch(gw.thread_unsubscribe(thread_id=thread_id, user_id=user.id), db=db)

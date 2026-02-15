import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import File, Message, Pin, Reaction, User, message_attachments
from vox.permissions import MANAGE_MESSAGES, READ_HISTORY, SEND_IN_THREADS, SEND_MESSAGES, has_permission, resolve_permissions
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.messages import (
    BulkDeleteRequest,
    EditMessageRequest,
    EditMessageResponse,
    MessageListResponse,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)

router = APIRouter(tags=["messages"])

# Simple snowflake: 42-bit timestamp (ms) + 22-bit sequence
_seq = 0
_last_ts = 0


def _snowflake() -> int:
    global _seq, _last_ts
    ts = int(time.time() * 1000)
    if ts == _last_ts:
        _seq += 1
    else:
        _seq = 0
        _last_ts = ts
    return (ts << 22) | (_seq & 0x3FFFFF)


def _msg_response(m: Message) -> MessageResponse:
    attachments = []
    if m.attachments:
        attachments = [
            {"file_id": f.id, "name": f.name, "size": f.size, "mime": f.mime, "url": f.url}
            for f in m.attachments
        ]
    return MessageResponse(
        msg_id=m.id,
        feed_id=m.feed_id,
        dm_id=m.dm_id,
        author_id=m.author_id,
        body=m.body,
        opaque_blob=m.opaque_blob,
        timestamp=m.timestamp,
        reply_to=m.reply_to,
        edit_timestamp=m.edit_timestamp,
        federated=m.federated,
        author_address=m.author_address,
        attachments=attachments,
    )


# --- Feed Messages ---

@router.get("/api/v1/feeds/{feed_id}/messages")
async def get_feed_messages(
    feed_id: int,
    limit: int = 50,
    before: int | None = None,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(READ_HISTORY, space_type="feed", space_id_param="feed_id"),
) -> MessageListResponse:
    query = select(Message).options(selectinload(Message.attachments)).where(Message.feed_id == feed_id, Message.thread_id == None).order_by(Message.id.desc()).limit(limit)
    if before is not None:
        query = query.where(Message.id < before)
    if after is not None:
        query = query.where(Message.id > after)
    result = await db.execute(query)
    return MessageListResponse(messages=[_msg_response(m) for m in result.scalars().all()])


@router.post("/api/v1/feeds/{feed_id}/messages", status_code=201)
async def send_feed_message(
    feed_id: int,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(SEND_MESSAGES, space_type="feed", space_id_param="feed_id"),
) -> SendMessageResponse:
    msg_id = _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(
        id=msg_id,
        feed_id=feed_id,
        author_id=user.id,
        body=body.body,
        timestamp=ts,
        reply_to=body.reply_to,
    )
    db.add(msg)
    await db.flush()
    if body.attachments:
        for file_id in body.attachments:
            f = (await db.execute(select(File).where(File.id == file_id))).scalar_one_or_none()
            if f is None:
                raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_ATTACHMENT", "message": f"File {file_id} not found."}})
            await db.execute(message_attachments.insert().values(msg_id=msg_id, file_id=file_id))
    await db.commit()
    await dispatch(gw.message_create(msg_id=msg_id, feed_id=feed_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to))
    return SendMessageResponse(msg_id=msg_id, timestamp=ts)


@router.patch("/api/v1/feeds/{feed_id}/messages/{msg_id}")
async def edit_feed_message(
    feed_id: int,
    msg_id: int,
    body: EditMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EditMessageResponse:
    result = await db.execute(select(Message).where(Message.id == msg_id, Message.feed_id == feed_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    if msg.author_id != user.id:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You can only edit your own messages."}})
    msg.body = body.body
    msg.edit_timestamp = int(time.time() * 1000)
    await db.commit()
    await dispatch(gw.message_update(msg_id=msg.id, feed_id=feed_id, body=body.body, edit_timestamp=msg.edit_timestamp))
    return EditMessageResponse(msg_id=msg.id, edit_timestamp=msg.edit_timestamp)


@router.delete("/api/v1/feeds/{feed_id}/messages/{msg_id}", status_code=204)
async def delete_feed_message(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Message).where(Message.id == msg_id, Message.feed_id == feed_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    # Author can always delete own messages; others need MANAGE_MESSAGES
    if msg.author_id != user.id:
        resolved = await resolve_permissions(db, user.id, space_type="feed", space_id=feed_id)
        if not has_permission(resolved, MANAGE_MESSAGES):
            raise HTTPException(status_code=403, detail={"error": {"code": "MISSING_PERMISSIONS", "message": "You lack the required permissions."}})
    await db.delete(msg)
    await db.commit()
    await dispatch(gw.message_delete(msg_id=msg_id, feed_id=feed_id))


@router.post("/api/v1/feeds/{feed_id}/messages/bulk-delete", status_code=204)
async def bulk_delete_messages(
    feed_id: int,
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_MESSAGES, space_type="feed", space_id_param="feed_id"),
):
    await db.execute(delete(Message).where(Message.id.in_(body.msg_ids), Message.feed_id == feed_id))
    await db.commit()
    await dispatch(gw.message_bulk_delete(feed_id=feed_id, msg_ids=body.msg_ids))


# --- Thread Messages ---

@router.get("/api/v1/feeds/{feed_id}/threads/{thread_id}/messages")
async def get_thread_messages(
    feed_id: int,
    thread_id: int,
    limit: int = 50,
    before: int | None = None,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageListResponse:
    query = select(Message).options(selectinload(Message.attachments)).where(Message.thread_id == thread_id).order_by(Message.id.desc()).limit(limit)
    if before is not None:
        query = query.where(Message.id < before)
    if after is not None:
        query = query.where(Message.id > after)
    result = await db.execute(query)
    return MessageListResponse(messages=[_msg_response(m) for m in result.scalars().all()])


@router.post("/api/v1/feeds/{feed_id}/threads/{thread_id}/messages", status_code=201)
async def send_thread_message(
    feed_id: int,
    thread_id: int,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(SEND_IN_THREADS, space_type="feed", space_id_param="feed_id"),
) -> SendMessageResponse:
    msg_id = _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(
        id=msg_id,
        feed_id=feed_id,
        thread_id=thread_id,
        author_id=user.id,
        body=body.body,
        timestamp=ts,
        reply_to=body.reply_to,
    )
    db.add(msg)
    await db.flush()
    if body.attachments:
        for file_id in body.attachments:
            f = (await db.execute(select(File).where(File.id == file_id))).scalar_one_or_none()
            if f is None:
                raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_ATTACHMENT", "message": f"File {file_id} not found."}})
            await db.execute(message_attachments.insert().values(msg_id=msg_id, file_id=file_id))
    await db.commit()
    await dispatch(gw.message_create(msg_id=msg_id, feed_id=feed_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to))
    return SendMessageResponse(msg_id=msg_id, timestamp=ts)


# --- Reactions ---

@router.put("/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}", status_code=204)
async def add_reaction(
    feed_id: int,
    msg_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db.add(Reaction(msg_id=msg_id, user_id=user.id, emoji=emoji))
    await db.commit()
    await dispatch(gw.message_reaction_add(msg_id=msg_id, user_id=user.id, emoji=emoji))


@router.delete("/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}", status_code=204)
async def remove_reaction(
    feed_id: int,
    msg_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(
        delete(Reaction).where(Reaction.msg_id == msg_id, Reaction.user_id == user.id, Reaction.emoji == emoji)
    )
    await db.commit()
    await dispatch(gw.message_reaction_remove(msg_id=msg_id, user_id=user.id, emoji=emoji))


# --- Pins ---

@router.put("/api/v1/feeds/{feed_id}/pins/{msg_id}", status_code=204)
async def pin_message(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from datetime import datetime, timezone
    db.add(Pin(feed_id=feed_id, msg_id=msg_id, pinned_at=datetime.now(timezone.utc)))
    await db.commit()
    await dispatch(gw.message_pin_update(msg_id=msg_id, feed_id=feed_id, pinned=True))


@router.delete("/api/v1/feeds/{feed_id}/pins/{msg_id}", status_code=204)
async def unpin_message(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await db.execute(delete(Pin).where(Pin.feed_id == feed_id, Pin.msg_id == msg_id))
    await db.commit()
    await dispatch(gw.message_pin_update(msg_id=msg_id, feed_id=feed_id, pinned=False))


@router.get("/api/v1/feeds/{feed_id}/pins")
async def list_pins(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageListResponse:
    result = await db.execute(
        select(Message).options(selectinload(Message.attachments)).join(Pin, Pin.msg_id == Message.id).where(Pin.feed_id == feed_id)
    )
    return MessageListResponse(messages=[_msg_response(m) for m in result.scalars().all()])

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.db.models import Message, Pin, Reaction, User
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
    )


# --- Feed Messages ---

@router.get("/api/v1/feeds/{feed_id}/messages")
async def get_feed_messages(
    feed_id: int,
    limit: int = 50,
    before: int | None = None,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageListResponse:
    # TODO: check READ_HISTORY permission
    query = select(Message).where(Message.feed_id == feed_id, Message.thread_id == None).order_by(Message.id.desc()).limit(limit)
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
    user: User = Depends(get_current_user),
) -> SendMessageResponse:
    # TODO: check SEND_MESSAGES permission
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
    await db.commit()
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
    # Author or MANAGE_MESSAGES permission can delete
    # TODO: check MANAGE_MESSAGES permission for non-authors
    if msg.author_id != user.id:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Insufficient permissions."}})
    await db.delete(msg)
    await db.commit()


@router.post("/api/v1/feeds/{feed_id}/messages/bulk-delete", status_code=204)
async def bulk_delete_messages(
    feed_id: int,
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # TODO: check MANAGE_MESSAGES permission
    await db.execute(delete(Message).where(Message.id.in_(body.msg_ids), Message.feed_id == feed_id))
    await db.commit()


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
    query = select(Message).where(Message.thread_id == thread_id).order_by(Message.id.desc()).limit(limit)
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
    user: User = Depends(get_current_user),
) -> SendMessageResponse:
    # TODO: check SEND_IN_THREADS permission
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
    await db.commit()
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


@router.delete("/api/v1/feeds/{feed_id}/pins/{msg_id}", status_code=204)
async def unpin_message(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await db.execute(delete(Pin).where(Pin.feed_id == feed_id, Pin.msg_id == msg_id))
    await db.commit()


@router.get("/api/v1/feeds/{feed_id}/pins")
async def list_pins(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageListResponse:
    result = await db.execute(
        select(Message).join(Pin, Pin.msg_id == Message.id).where(Pin.feed_id == feed_id)
    )
    return MessageListResponse(messages=[_msg_response(m) for m in result.scalars().all()])

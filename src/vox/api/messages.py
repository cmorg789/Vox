import asyncio
import ipaddress
import json
import socket
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Bot, BotCommand, Feed, File, Message, Pin, Reaction, Thread, User, message_attachments
from vox.config import config
from vox.permissions import ADD_REACTIONS, MANAGE_MESSAGES, MANAGE_SPACES, MENTION_EVERYONE, READ_HISTORY, SEND_EMBEDS, SEND_IN_THREADS, SEND_MESSAGES, has_permission, resolve_permissions
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.gateway.notify import notify_for_message, notify_for_reaction
from vox import interactions
from vox.models.messages import (
    BulkDeleteRequest,
    EditMessageRequest,
    EditMessageResponse,
    MessageListResponse,
    MessageResponse,
    ReactionGroup,
    ReactionListResponse,
    SendMessageRequest,
    SendMessageResponse,
)

router = APIRouter(tags=["messages"])


async def _is_safe_url(url: str) -> tuple[bool, str, str]:
    """Validate a URL is safe to call (SSRF prevention).

    Returns (is_safe, resolved_ip, hostname).  The caller should connect to
    ``resolved_ip`` directly with a ``Host`` header to prevent DNS rebinding.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        return False, "", ""
    hostname = parsed.hostname or ""
    loop = asyncio.get_running_loop()
    try:
        addrinfos = await loop.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, "", ""
    resolved_ip: str = ""
    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False, "", ""
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False, "", ""
        if not resolved_ip:
            resolved_ip = str(addr)
    return True, resolved_ip, hostname

# Simple snowflake: 42-bit timestamp (ms) + 22-bit sequence
_seq = 0
_last_ts = 0
_snowflake_lock = asyncio.Lock()


async def _snowflake() -> int:
    global _seq, _last_ts
    async with _snowflake_lock:
        ts = int(time.time() * 1000)
        if ts == _last_ts:
            _seq += 1
        else:
            _seq = 0
            _last_ts = ts
        return (ts << 22) | (_seq & 0x3FFFFF)


async def _update_search_vector(db, msg_id: int, body: str | None) -> None:
    """Populate the search_vector column on PostgreSQL. No-op on SQLite."""
    from vox.db.engine import get_engine
    if get_engine().dialect.name != "postgresql" or not body:
        return
    from sqlalchemy import func, update
    await db.execute(
        update(Message)
        .where(Message.id == msg_id)
        .values(search_vector=func.to_tsvector("english", body))
    )


def _msg_response(m: Message) -> MessageResponse:
    from vox.models.bots import Embed
    from vox.models.files import FileResponse

    attachments = []
    if m.attachments:
        attachments = [
            FileResponse(file_id=f.id, name=f.name, size=f.size, mime=f.mime, url=f.url)
            for f in m.attachments
        ]
    embed = None
    if m.embed:
        try:
            embed = Embed.model_validate_json(m.embed)
        except Exception:
            pass
    return MessageResponse(
        msg_id=m.id,
        feed_id=m.feed_id,
        dm_id=m.dm_id,
        thread_id=m.thread_id,
        author_id=m.author_id,
        body=m.body,
        opaque_blob=m.opaque_blob,
        timestamp=m.timestamp,
        reply_to=m.reply_to,
        edit_timestamp=m.edit_timestamp,
        federated=m.federated,
        author_address=m.author_address,
        attachments=attachments,
        embed=embed,
        webhook_id=m.webhook_id,
    )


def _parse_slash_command(text: str) -> tuple[str, dict] | None:
    """Parse '/command param1=val1 param2=val2' into (name, params)."""
    if not text.startswith("/"):
        return None
    parts = text.split()
    name = parts[0][1:]  # strip leading /
    if not name:
        return None
    params: dict = {}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = v
        else:
            params[part] = True
    return name, params


async def _handle_slash_command(
    text: str,
    user: User,
    feed_id: int | None,
    dm_id: int | None,
    db: AsyncSession,
) -> SendMessageResponse | None:
    """If text is a slash command, intercept and create interaction. Returns response or None."""
    if not text:
        return None
    parsed = _parse_slash_command(text)
    if parsed is None:
        return None
    cmd_name, params = parsed

    # Look up the command
    result = await db.execute(select(BotCommand).where(BotCommand.name == cmd_name))
    bot_cmd = result.scalar_one_or_none()
    if bot_cmd is None:
        return None  # Not a registered command, treat as normal message

    # Get the bot
    result = await db.execute(select(Bot).where(Bot.id == bot_cmd.bot_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        return None  # Bot was deleted, treat as normal message

    interaction = interactions.create(
        type="slash_command",
        command=cmd_name,
        params=params,
        user_id=user.id,
        feed_id=feed_id,
        dm_id=dm_id,
        bot_id=bot.id,
    )

    payload = {
        "id": interaction.id,
        "type": "slash_command",
        "command": cmd_name,
        "params": params,
        "user_id": user.id,
        "feed_id": feed_id,
        "dm_id": dm_id,
    }

    if bot.interaction_url:
        # HTTP callback bot — validate URL to prevent SSRF
        safe, resolved_ip, host = await _is_safe_url(bot.interaction_url)
        if not safe:
            return None
        try:
            pinned_url = bot.interaction_url.replace(f"://{host}", f"://{resolved_ip}", 1)
            async with httpx.AsyncClient() as client:
                resp = await client.post(pinned_url, json=payload, timeout=5.0, headers={"Host": host})
                if resp.status_code == 200 and resp.content:
                    data = resp.json()
                    if data.get("body"):
                        # Create message from bot response
                        msg_id = await _snowflake()
                        ts = int(time.time() * 1000)
                        msg = Message(
                            id=msg_id,
                            feed_id=feed_id,
                            dm_id=dm_id,
                            author_id=bot.user_id,
                            body=data["body"],
                            timestamp=ts,
                        )
                        db.add(msg)
                        await db.commit()
                        await dispatch(gw.message_create(
                            msg_id=msg_id, feed_id=feed_id, dm_id=dm_id,
                            author_id=bot.user_id, body=data["body"], timestamp=ts,
                        ), db=db)
        except httpx.HTTPError:
            # Dispatch ephemeral error to the invoking user
            error_msg_id = await _snowflake()
            error_ts = int(time.time() * 1000)
            await dispatch(
                gw.message_create(
                    msg_id=error_msg_id,
                    feed_id=feed_id,
                    dm_id=dm_id,
                    author_id=None,
                    body="Bot did not respond. Please try again later.",
                    timestamp=error_ts,
                ),
                user_ids=[user.id],
                db=db,
            )
    else:
        # Gateway bot — dispatch interaction_create to the bot's user
        await dispatch(
            gw.interaction_create(payload),
            user_ids=[bot.user_id],
            db=db,
        )

    return SendMessageResponse(msg_id=0, timestamp=int(time.time() * 1000), interaction_id=interaction.id)


# --- Feed Messages ---

@router.get("/api/v1/feeds/{feed_id}/messages")
async def get_feed_messages(
    feed_id: int,
    limit: int = Query(default=50, ge=1, le=1000),
    before: int | None = None,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(READ_HISTORY, space_type="feed", space_id_param="feed_id"),
) -> MessageListResponse:
    limit = min(limit, config.limits.page_limit_messages)
    query = select(Message).options(selectinload(Message.attachments)).where(Message.feed_id == feed_id, Message.thread_id == None).order_by(Message.id.desc()).limit(limit)
    if before is not None:
        query = query.where(Message.id < before)
    if after is not None:
        query = query.where(Message.id > after)
    result = await db.execute(query)
    return MessageListResponse(messages=[_msg_response(m) for m in result.scalars().all()])


@router.get("/api/v1/feeds/{feed_id}/messages/{msg_id}")
async def get_feed_message(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(READ_HISTORY, space_type="feed", space_id_param="feed_id"),
) -> MessageResponse:
    result = await db.execute(select(Message).options(selectinload(Message.attachments)).where(Message.id == msg_id, Message.feed_id == feed_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    return _msg_response(msg)


@router.get("/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions")
async def list_message_reactions(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(READ_HISTORY, space_type="feed", space_id_param="feed_id"),
) -> ReactionListResponse:
    msg = (await db.execute(select(Message).where(Message.id == msg_id, Message.feed_id == feed_id))).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    result = await db.execute(select(Reaction).where(Reaction.msg_id == msg_id))
    reactions = result.scalars().all()
    grouped: dict[str, list[int]] = {}
    for r in reactions:
        grouped.setdefault(r.emoji, []).append(r.user_id)
    return ReactionListResponse(reactions=[ReactionGroup(emoji=emoji, user_ids=uids) for emoji, uids in grouped.items()])


@router.post("/api/v1/feeds/{feed_id}/messages", status_code=201)
async def send_feed_message(
    feed_id: int,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(SEND_MESSAGES, space_type="feed", space_id_param="feed_id"),
) -> SendMessageResponse:
    # Fetch the feed to check type-based restrictions
    feed = (await db.execute(select(Feed).where(Feed.id == feed_id))).scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Feed not found."}})

    # Empty message validation
    if not (body.body and body.body.strip()) and not body.attachments and not getattr(body, "embed", None):
        raise HTTPException(status_code=400, detail={"error": {"code": "EMPTY_MESSAGE", "message": "Message must have body, attachments, or embed."}})
    if body.body and len(body.body) > config.limits.message_body_max:
        raise HTTPException(status_code=400, detail={"error": {"code": "MESSAGE_TOO_LARGE", "message": f"Message body exceeds maximum of {config.limits.message_body_max} characters."}})

    # Resolve permissions once for all checks in this handler
    perms = await resolve_permissions(db, user.id, space_type="feed", space_id=feed_id)

    # Announcement feeds: only users with MANAGE_SPACES can post
    if feed.type == "announcement":
        if not has_permission(perms, MANAGE_SPACES):
            raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Only moderators can post in announcement feeds."}})

    # Slash command interception
    intercepted = await _handle_slash_command(body.body, user, feed_id=feed_id, dm_id=None, db=db)
    if intercepted is not None:
        return intercepted

    # Strip @everyone sentinel if user lacks MENTION_EVERYONE permission
    if body.mentions and 0 in body.mentions:
        if not has_permission(perms, MENTION_EVERYONE):
            body.mentions = [uid for uid in body.mentions if uid != 0]

    # Check SEND_EMBEDS permission if embed provided
    embed = body.embed
    if embed is not None:
        if not has_permission(perms, SEND_EMBEDS):
            embed = None  # Silently strip embed if user lacks permission

    msg_id = await _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(
        id=msg_id,
        feed_id=feed_id,
        author_id=user.id,
        body=body.body,
        timestamp=ts,
        reply_to=body.reply_to,
        embed=embed,
    )
    db.add(msg)
    await db.flush()

    # Populate FTS search_vector on PostgreSQL
    await _update_search_vector(db, msg_id, body.body)

    attachment_dicts = []
    if body.attachments:
        files = (await db.execute(select(File).where(File.id.in_(body.attachments)))).scalars().all()
        files_by_id = {f.id: f for f in files}
        for file_id in body.attachments:
            f = files_by_id.get(file_id)
            if f is None:
                raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_ATTACHMENT", "message": f"File {file_id} not found."}})
            if f.uploader_id != user.id and f.feed_id != feed_id:
                raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this file."}})
            await db.execute(message_attachments.insert().values(msg_id=msg_id, file_id=file_id))
            attachment_dicts.append({"file_id": f.id, "name": f.name, "size": f.size, "mime": f.mime, "url": f.url})

    # Forum feeds: auto-create a thread for each new message
    forum_thread = None
    if feed.type == "forum":
        thread_name = (body.body[:64] if body.body else "Thread")
        forum_thread = Thread(
            name=thread_name,
            feed_id=feed_id,
            parent_msg_id=msg_id,
        )
        db.add(forum_thread)
        await db.flush()

    await db.commit()
    # Dispatch thread_create before message_create so clients know the thread exists
    if forum_thread is not None:
        await dispatch(gw.thread_create(
            thread_id=forum_thread.id,
            parent_feed_id=feed_id,
            parent_msg_id=msg_id,
            name=forum_thread.name,
        ), db=db)
    embed_dict = json.loads(embed) if embed and isinstance(embed, str) else embed
    await dispatch(gw.message_create(msg_id=msg_id, feed_id=feed_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to, mentions=body.mentions, embed=embed_dict, attachments=attachment_dicts or None), db=db)
    await notify_for_message(db, msg_id=msg_id, feed_id=feed_id, thread_id=None, dm_id=None, author_id=user.id, body=body.body, reply_to=body.reply_to, mentions=body.mentions)
    return SendMessageResponse(msg_id=msg_id, timestamp=ts, mentions=body.mentions)


@router.patch("/api/v1/feeds/{feed_id}/messages/{msg_id}")
async def edit_feed_message(
    feed_id: int,
    msg_id: int,
    body: EditMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(SEND_MESSAGES, space_type="feed", space_id_param="feed_id"),
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
    await dispatch(gw.message_update(msg_id=msg.id, feed_id=feed_id, body=body.body, edit_timestamp=msg.edit_timestamp), db=db)
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
    await dispatch(gw.message_delete(msg_id=msg_id, feed_id=feed_id), db=db)


@router.post("/api/v1/feeds/{feed_id}/messages/bulk-delete", status_code=204)
async def bulk_delete_messages(
    feed_id: int,
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_MESSAGES, space_type="feed", space_id_param="feed_id"),
):
    await db.execute(delete(Message).where(Message.id.in_(body.msg_ids), Message.feed_id == feed_id))
    await db.commit()
    await dispatch(gw.message_bulk_delete(feed_id=feed_id, msg_ids=body.msg_ids), db=db)


# --- Thread Messages ---

@router.get("/api/v1/feeds/{feed_id}/threads/{thread_id}/messages")
async def get_thread_messages(
    feed_id: int,
    thread_id: int,
    limit: int = Query(default=50, ge=1, le=1000),
    before: int | None = None,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(READ_HISTORY, space_type="feed", space_id_param="feed_id"),
) -> MessageListResponse:
    # Validate thread exists and belongs to feed
    thread = (await db.execute(select(Thread).where(Thread.id == thread_id))).scalar_one_or_none()
    if thread is None or thread.feed_id != feed_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist in this feed."}})
    limit = min(limit, config.limits.page_limit_messages)
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
    # Validate thread exists, belongs to feed, and is not locked
    thread = (await db.execute(select(Thread).where(Thread.id == thread_id))).scalar_one_or_none()
    if thread is None or thread.feed_id != feed_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Thread does not exist in this feed."}})
    if thread.locked:
        raise HTTPException(status_code=403, detail={"error": {"code": "THREAD_LOCKED", "message": "This thread is locked."}})
    # Empty message validation
    if not (body.body and body.body.strip()) and not body.attachments and not getattr(body, "embed", None):
        raise HTTPException(status_code=400, detail={"error": {"code": "EMPTY_MESSAGE", "message": "Message must have body, attachments, or embed."}})
    if body.body and len(body.body) > config.limits.message_body_max:
        raise HTTPException(status_code=400, detail={"error": {"code": "MESSAGE_TOO_LARGE", "message": f"Message body exceeds maximum of {config.limits.message_body_max} characters."}})
    # Slash command interception
    intercepted = await _handle_slash_command(body.body, user, feed_id=feed_id, dm_id=None, db=db)
    if intercepted is not None:
        return intercepted

    # Strip @everyone sentinel if user lacks MENTION_EVERYONE permission
    if body.mentions and 0 in body.mentions:
        perms = await resolve_permissions(db, user.id, space_type="feed", space_id=feed_id)
        if not has_permission(perms, MENTION_EVERYONE):
            body.mentions = [uid for uid in body.mentions if uid != 0]

    # Check SEND_EMBEDS permission if embed provided
    embed = body.embed
    if embed is not None:
        perms = await resolve_permissions(db, user.id, space_type="feed", space_id=feed_id)
        if not has_permission(perms, SEND_EMBEDS):
            embed = None

    msg_id = await _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(
        id=msg_id,
        feed_id=feed_id,
        thread_id=thread_id,
        author_id=user.id,
        body=body.body,
        timestamp=ts,
        reply_to=body.reply_to,
        embed=embed,
    )
    db.add(msg)
    await db.flush()

    # Populate FTS search_vector on PostgreSQL
    await _update_search_vector(db, msg_id, body.body)

    attachment_dicts = []
    if body.attachments:
        files = (await db.execute(select(File).where(File.id.in_(body.attachments)))).scalars().all()
        files_by_id = {f.id: f for f in files}
        for file_id in body.attachments:
            f = files_by_id.get(file_id)
            if f is None:
                raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_ATTACHMENT", "message": f"File {file_id} not found."}})
            if f.uploader_id != user.id and f.feed_id != feed_id:
                raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this file."}})
            await db.execute(message_attachments.insert().values(msg_id=msg_id, file_id=file_id))
            attachment_dicts.append({"file_id": f.id, "name": f.name, "size": f.size, "mime": f.mime, "url": f.url})
    await db.commit()
    embed_dict = json.loads(embed) if embed and isinstance(embed, str) else embed
    await dispatch(gw.message_create(msg_id=msg_id, feed_id=feed_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to, mentions=body.mentions, embed=embed_dict, attachments=attachment_dicts or None), db=db)
    await notify_for_message(db, msg_id=msg_id, feed_id=feed_id, thread_id=thread_id, dm_id=None, author_id=user.id, body=body.body, reply_to=body.reply_to, mentions=body.mentions)
    return SendMessageResponse(msg_id=msg_id, timestamp=ts, mentions=body.mentions)


# --- Reactions ---

@router.put("/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}", status_code=204)
async def add_reaction(
    feed_id: int,
    msg_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(ADD_REACTIONS, space_type="feed", space_id_param="feed_id"),
):
    from vox.db.engine import dialect_insert
    msg = (await db.execute(select(Message).where(Message.id == msg_id, Message.feed_id == feed_id))).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    stmt = dialect_insert(Reaction).values(msg_id=msg_id, user_id=user.id, emoji=emoji).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()
    await dispatch(gw.message_reaction_add(msg_id=msg_id, user_id=user.id, emoji=emoji), db=db)
    await notify_for_reaction(db, msg_id=msg_id, reactor_id=user.id, emoji=emoji)


@router.delete("/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}", status_code=204)
async def remove_reaction(
    feed_id: int,
    msg_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(READ_HISTORY, space_type="feed", space_id_param="feed_id"),
):
    msg = (await db.execute(select(Message).where(Message.id == msg_id, Message.feed_id == feed_id))).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    await db.execute(
        delete(Reaction).where(Reaction.msg_id == msg_id, Reaction.user_id == user.id, Reaction.emoji == emoji)
    )
    await db.commit()
    await dispatch(gw.message_reaction_remove(msg_id=msg_id, user_id=user.id, emoji=emoji), db=db)


# --- Pins ---

@router.put("/api/v1/feeds/{feed_id}/pins/{msg_id}", status_code=204)
async def pin_message(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_MESSAGES, space_type="feed", space_id_param="feed_id"),
):
    from datetime import datetime, timezone
    from sqlalchemy import func
    from vox.db.engine import dialect_insert
    # Enforce pin cap
    pin_count = (await db.execute(
        select(func.count()).select_from(Pin).where(Pin.feed_id == feed_id)
    )).scalar() or 0
    if pin_count >= config.limits.max_pins_per_feed:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "PIN_LIMIT_REACHED", "message": f"Maximum of {config.limits.max_pins_per_feed} pins per feed."}},
        )
    stmt = dialect_insert(Pin).values(feed_id=feed_id, msg_id=msg_id, pinned_at=datetime.now(timezone.utc)).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()
    await dispatch(gw.message_pin_update(msg_id=msg_id, feed_id=feed_id, pinned=True), db=db)


@router.delete("/api/v1/feeds/{feed_id}/pins/{msg_id}", status_code=204)
async def unpin_message(
    feed_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_MESSAGES, space_type="feed", space_id_param="feed_id"),
):
    await db.execute(delete(Pin).where(Pin.feed_id == feed_id, Pin.msg_id == msg_id))
    await db.commit()
    await dispatch(gw.message_pin_update(msg_id=msg_id, feed_id=feed_id, pinned=False), db=db)


@router.get("/api/v1/feeds/{feed_id}/pins")
async def list_pins(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(READ_HISTORY, space_type="feed", space_id_param="feed_id"),
) -> MessageListResponse:
    result = await db.execute(
        select(Message, Pin.pinned_at).options(selectinload(Message.attachments)).join(Pin, Pin.msg_id == Message.id).where(Pin.feed_id == feed_id)
    )
    messages = []
    for m, pinned_at in result.all():
        resp = _msg_response(m)
        resp.pinned_at = int(pinned_at.timestamp()) if pinned_at else None
        messages.append(resp)
    return MessageListResponse(messages=messages)

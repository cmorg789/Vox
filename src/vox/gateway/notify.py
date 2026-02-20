"""Targeted notification delivery for messages and reactions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.db.models import Message, Role, dm_participants, feed_subscribers, role_members, thread_subscribers
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch


def _preview(body: str | None, limit: int = 100) -> str | None:
    if body is None:
        return None
    return body[:limit] if len(body) <= limit else body[:limit - 1] + "\u2026"


async def notify_for_message(
    db: AsyncSession,
    msg_id: int,
    feed_id: int | None,
    thread_id: int | None,
    dm_id: int | None,
    author_id: int,
    body: str | None,
    reply_to: int | None,
    mentions: list[int] | None,
) -> None:
    preview = _preview(body)

    # Collect mention IDs (exclude author)
    mention_ids: set[int] = set()
    if mentions:
        working = list(mentions)
        if 0 in working:
            working = [uid for uid in working if uid != 0]
            if dm_id is not None:
                # Expand to all DM participants
                result = await db.execute(
                    select(dm_participants.c.user_id).where(dm_participants.c.dm_id == dm_id)
                )
                everyone = {r[0] for r in result.all()}
            else:
                # Expand to all server members via @everyone role (position=0)
                result = await db.execute(
                    select(role_members.c.user_id)
                    .join(Role, Role.id == role_members.c.role_id)
                    .where(Role.position == 0)
                )
                everyone = {r[0] for r in result.all()}
            mention_ids = everyone - {author_id}
        mention_ids |= {uid for uid in working if uid != author_id}

    # Collect reply-to author
    reply_id: int | None = None
    if reply_to is not None:
        result = await db.execute(select(Message.author_id).where(Message.id == reply_to))
        row = result.scalar_one_or_none()
        if row is not None and row != author_id and row not in mention_ids:
            reply_id = row

    # Collect subscriber IDs (exclude author, mentions, reply)
    subscriber_ids: set[int] = set()
    if feed_id is not None and thread_id is None:
        result = await db.execute(
            select(feed_subscribers.c.user_id).where(feed_subscribers.c.feed_id == feed_id)
        )
        subscriber_ids = {r[0] for r in result.all()}
    if thread_id is not None:
        result = await db.execute(
            select(thread_subscribers.c.user_id).where(thread_subscribers.c.thread_id == thread_id)
        )
        subscriber_ids = {r[0] for r in result.all()}
    subscriber_ids -= {author_id}
    subscriber_ids -= mention_ids
    if reply_id is not None:
        subscriber_ids.discard(reply_id)

    # Batch dispatch notifications — collect all recipients, deduplicate, single call per type
    all_recipients: dict[int, str] = {}  # user_id -> notification type

    for uid in mention_ids:
        all_recipients[uid] = "mention"
    if reply_id is not None and reply_id not in all_recipients:
        all_recipients[reply_id] = "reply"
    for uid in subscriber_ids:
        if uid not in all_recipients:
            all_recipients[uid] = "message"

    # Group by type and batch dispatch
    by_type: dict[str, list[int]] = {}
    for uid, ntype in all_recipients.items():
        by_type.setdefault(ntype, []).append(uid)

    for ntype, uids in by_type.items():
        for uid in uids:
            await dispatch(
                gw.notification_create(
                    user_id=uid, type=ntype, feed_id=feed_id, thread_id=thread_id,
                    msg_id=msg_id, actor_id=author_id, body_preview=preview,
                ),
                user_ids=[uid],
            )


async def notify_for_reaction(
    db: AsyncSession,
    msg_id: int,
    reactor_id: int,
    emoji: str,
) -> None:
    result = await db.execute(
        select(Message.author_id, Message.feed_id, Message.thread_id, Message.dm_id)
        .where(Message.id == msg_id)
    )
    row = result.one_or_none()
    if row is None:
        return
    author_id, feed_id, thread_id, dm_id = row
    if author_id == reactor_id:
        return
    await dispatch(
        gw.notification_create(
            user_id=author_id, type="reaction", feed_id=feed_id, thread_id=thread_id,
            msg_id=msg_id, actor_id=reactor_id, body_preview=emoji,
        ),
        user_ids=[author_id],
    )

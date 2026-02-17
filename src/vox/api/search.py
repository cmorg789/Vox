from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vox.api.deps import get_current_user, get_db
from vox.api.messages import _msg_response
from vox.db.models import Feed, Message, Pin, User, message_attachments
from vox.limits import limits
from vox.models.messages import SearchResponse
from vox.permissions import VIEW_SPACE, has_permission, resolve_permissions

router = APIRouter(tags=["search"])


@router.get("/api/v1/messages/search")
async def search_messages(
    query: str,
    feed_id: int | None = None,
    author_id: int | None = None,
    before: int | None = None,
    after: int | None = None,
    has_file: bool | None = None,
    has_embed: bool | None = None,
    pinned: bool | None = None,
    thread_id: int | None = None,
    limit: int = Query(default=25, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchResponse:
    limit = min(limit, limits.page_limit_search)

    # Build set of accessible feeds for this user
    all_feeds = (await db.execute(select(Feed.id))).scalars().all()
    accessible_feeds = []
    for fid in all_feeds:
        resolved = await resolve_permissions(db, user.id, space_type="feed", space_id=fid)
        if has_permission(resolved, VIEW_SPACE):
            accessible_feeds.append(fid)

    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    stmt = select(Message).options(selectinload(Message.attachments)).where(Message.body.ilike(f"%{escaped}%", escape="\\")).order_by(Message.id.desc()).limit(limit)

    # Only search accessible feeds (exclude DM messages from search)
    stmt = stmt.where(Message.feed_id.in_(accessible_feeds))

    if feed_id is not None:
        stmt = stmt.where(Message.feed_id == feed_id)
    if thread_id is not None:
        stmt = stmt.where(Message.thread_id == thread_id)
    if author_id is not None:
        stmt = stmt.where(Message.author_id == author_id)
    if before is not None:
        stmt = stmt.where(Message.id < before)
    if after is not None:
        stmt = stmt.where(Message.id > after)
    if pinned is True:
        stmt = stmt.join(Pin, Pin.msg_id == Message.id)
    if has_file is True:
        stmt = stmt.join(message_attachments, message_attachments.c.msg_id == Message.id)
    if has_file is False:
        from sqlalchemy import not_, exists
        attachment_exists = select(message_attachments.c.msg_id).where(
            message_attachments.c.msg_id == Message.id
        ).exists()
        stmt = stmt.where(not_(attachment_exists))
    if has_embed is True:
        stmt = stmt.where(Message.embed != None)
    if has_embed is False:
        stmt = stmt.where(Message.embed == None)
    result = await db.execute(stmt)
    return SearchResponse(results=[_msg_response(m) for m in result.scalars().all()])

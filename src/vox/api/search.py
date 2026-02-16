from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vox.api.deps import get_current_user, get_db
from vox.api.messages import _msg_response
from vox.db.models import Message, Pin, User, message_attachments
from vox.limits import PAGE_LIMIT_SEARCH
from vox.models.messages import SearchResponse

router = APIRouter(tags=["search"])


@router.get("/api/v1/messages/search")
async def search_messages(
    query: str,
    feed_id: int | None = None,
    author_id: int | None = None,
    before: int | None = None,
    after: int | None = None,
    has_file: bool | None = None,
    pinned: bool | None = None,
    limit: int = Query(default=25, ge=1, le=PAGE_LIMIT_SEARCH),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SearchResponse:
    stmt = select(Message).options(selectinload(Message.attachments)).where(Message.body.ilike(f"%{query}%")).order_by(Message.id.desc()).limit(limit)
    if feed_id is not None:
        stmt = stmt.where(Message.feed_id == feed_id)
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
    result = await db.execute(stmt)
    return SearchResponse(results=[_msg_response(m) for m in result.scalars().all()])

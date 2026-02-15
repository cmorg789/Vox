from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Emoji, Sticker, User
from vox.permissions import MANAGE_EMOJI
from vox.models.emoji import EmojiResponse, StickerResponse
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch

router = APIRouter(tags=["emoji"])


# --- Emoji ---

@router.get("/api/v1/emoji")
async def list_emoji(
    limit: int = 100,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(Emoji).order_by(Emoji.id).limit(limit)
    if after is not None:
        query = query.where(Emoji.id > after)
    result = await db.execute(query)
    emoji = result.scalars().all()
    items = [EmojiResponse(emoji_id=e.id, name=e.name, creator_id=e.creator_id) for e in emoji]
    cursor = str(emoji[-1].id) if emoji else None
    return {"items": items, "cursor": cursor}


@router.post("/api/v1/emoji", status_code=201)
async def create_emoji(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(MANAGE_EMOJI),
) -> EmojiResponse:
    emoji = Emoji(name=name, creator_id=user.id, image="")  # image set via file upload
    db.add(emoji)
    await db.flush()
    await db.commit()
    await dispatch(gw.emoji_create(emoji_id=emoji.id, name=emoji.name, creator_id=emoji.creator_id))
    return EmojiResponse(emoji_id=emoji.id, name=emoji.name, creator_id=emoji.creator_id)


@router.delete("/api/v1/emoji/{emoji_id}", status_code=204)
async def delete_emoji(
    emoji_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_EMOJI),
):
    result = await db.execute(select(Emoji).where(Emoji.id == emoji_id))
    emoji = result.scalar_one_or_none()
    if emoji is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Emoji not found."}})
    await db.delete(emoji)
    await db.commit()
    await dispatch(gw.emoji_delete(emoji_id=emoji_id))


# --- Stickers ---

@router.get("/api/v1/stickers")
async def list_stickers(
    limit: int = 100,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(Sticker).order_by(Sticker.id).limit(limit)
    if after is not None:
        query = query.where(Sticker.id > after)
    result = await db.execute(query)
    stickers = result.scalars().all()
    items = [StickerResponse(sticker_id=s.id, name=s.name, creator_id=s.creator_id) for s in stickers]
    cursor = str(stickers[-1].id) if stickers else None
    return {"items": items, "cursor": cursor}


@router.post("/api/v1/stickers", status_code=201)
async def create_sticker(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(MANAGE_EMOJI),
) -> StickerResponse:
    sticker = Sticker(name=name, creator_id=user.id, image="")
    db.add(sticker)
    await db.flush()
    await db.commit()
    await dispatch(gw.sticker_create(sticker_id=sticker.id, name=sticker.name, creator_id=sticker.creator_id))
    return StickerResponse(sticker_id=sticker.id, name=sticker.name, creator_id=sticker.creator_id)


@router.delete("/api/v1/stickers/{sticker_id}", status_code=204)
async def delete_sticker(
    sticker_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_EMOJI),
):
    result = await db.execute(select(Sticker).where(Sticker.id == sticker_id))
    sticker = result.scalar_one_or_none()
    if sticker is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Sticker not found."}})
    await db.delete(sticker)
    await db.commit()
    await dispatch(gw.sticker_delete(sticker_id=sticker_id))

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.storage import get_storage
from vox.db.models import Emoji, File, Sticker, User
from vox.config import check_mime, config
from vox.permissions import MANAGE_EMOJI
from vox.models.emoji import EmojiListResponse, EmojiResponse, StickerListResponse, StickerResponse, UpdateEmojiRequest, UpdateStickerRequest
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch

router = APIRouter(tags=["emoji"])


# --- Emoji ---

@router.get("/api/v1/emoji")
async def list_emoji(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EmojiListResponse:
    limit = min(limit, config.limits.page_limit_emoji)
    query = select(Emoji).order_by(Emoji.id).limit(limit)
    if after is not None:
        query = query.where(Emoji.id > after)
    result = await db.execute(query)
    emoji = result.scalars().all()
    items = [EmojiResponse(emoji_id=e.id, name=e.name, creator_id=e.creator_id, image=e.image) for e in emoji]
    cursor = str(emoji[-1].id) if emoji else None
    return EmojiListResponse(items=items, cursor=cursor)


@router.post("/api/v1/emoji", status_code=201)
async def create_emoji(
    image: UploadFile,
    name: str = Form(),
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(MANAGE_EMOJI),
) -> EmojiResponse:
    content = await image.read()
    if len(content) > config.limits.file_upload_max_bytes:
        raise HTTPException(status_code=413, detail={"error": {"code": "FILE_TOO_LARGE", "message": f"File exceeds {config.limits.file_upload_max_bytes} byte limit."}})
    emoji_mime = image.content_type or "application/octet-stream"
    if not check_mime(emoji_mime, config.media.allowed_emoji_mimes):
        raise HTTPException(status_code=415, detail={"error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": f"MIME type '{emoji_mime}' is not allowed for emoji."}})
    file_id = secrets.token_urlsafe(16)
    storage = get_storage()
    image_url = await storage.put(file_id, content, emoji_mime)
    file_row = File(
        id=file_id,
        name=f"{name}.emoji",
        size=len(content),
        mime=emoji_mime,
        url=image_url,
        uploader_id=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(file_row)
    emoji = Emoji(name=name, creator_id=user.id, image=image_url)
    db.add(emoji)
    await db.flush()
    await db.commit()
    await dispatch(gw.emoji_create(emoji_id=emoji.id, name=emoji.name, creator_id=emoji.creator_id, image=image_url), db=db)
    return EmojiResponse(emoji_id=emoji.id, name=emoji.name, creator_id=emoji.creator_id, image=image_url)


@router.patch("/api/v1/emoji/{emoji_id}")
async def update_emoji(
    emoji_id: int,
    body: UpdateEmojiRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_EMOJI),
) -> EmojiResponse:
    result = await db.execute(select(Emoji).where(Emoji.id == emoji_id))
    emoji = result.scalar_one_or_none()
    if emoji is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Emoji not found."}})
    emoji.name = body.name
    await db.commit()
    await dispatch(gw.emoji_update(emoji_id=emoji_id, name=body.name), db=db)
    return EmojiResponse(emoji_id=emoji.id, name=emoji.name, creator_id=emoji.creator_id, image=emoji.image)


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
    # Clean up storage and file record
    if emoji.image:
        file_key = emoji.image.rsplit("/", 1)[-1]
        storage = get_storage()
        try:
            await storage.delete(file_key)
        except Exception:
            pass
        file_row = await db.get(File, file_key)
        if file_row:
            await db.delete(file_row)
    await db.delete(emoji)
    await db.commit()
    await dispatch(gw.emoji_delete(emoji_id=emoji_id), db=db)


# --- Stickers ---

@router.get("/api/v1/stickers")
async def list_stickers(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StickerListResponse:
    limit = min(limit, config.limits.page_limit_stickers)
    query = select(Sticker).order_by(Sticker.id).limit(limit)
    if after is not None:
        query = query.where(Sticker.id > after)
    result = await db.execute(query)
    stickers = result.scalars().all()
    items = [StickerResponse(sticker_id=s.id, name=s.name, creator_id=s.creator_id, image=s.image) for s in stickers]
    cursor = str(stickers[-1].id) if stickers else None
    return StickerListResponse(items=items, cursor=cursor)


@router.post("/api/v1/stickers", status_code=201)
async def create_sticker(
    image: UploadFile,
    name: str = Form(),
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(MANAGE_EMOJI),
) -> StickerResponse:
    content = await image.read()
    if len(content) > config.limits.file_upload_max_bytes:
        raise HTTPException(status_code=413, detail={"error": {"code": "FILE_TOO_LARGE", "message": f"File exceeds {config.limits.file_upload_max_bytes} byte limit."}})
    sticker_mime = image.content_type or "application/octet-stream"
    if not check_mime(sticker_mime, config.media.allowed_sticker_mimes):
        raise HTTPException(status_code=415, detail={"error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": f"MIME type '{sticker_mime}' is not allowed for stickers."}})
    file_id = secrets.token_urlsafe(16)
    storage = get_storage()
    image_url = await storage.put(file_id, content, sticker_mime)
    file_row = File(
        id=file_id,
        name=f"{name}.sticker",
        size=len(content),
        mime=sticker_mime,
        url=image_url,
        uploader_id=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(file_row)
    sticker = Sticker(name=name, creator_id=user.id, image=image_url)
    db.add(sticker)
    await db.flush()
    await db.commit()
    await dispatch(gw.sticker_create(sticker_id=sticker.id, name=sticker.name, creator_id=sticker.creator_id, image=image_url), db=db)
    return StickerResponse(sticker_id=sticker.id, name=sticker.name, creator_id=sticker.creator_id, image=image_url)


@router.patch("/api/v1/stickers/{sticker_id}")
async def update_sticker(
    sticker_id: int,
    body: UpdateStickerRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_EMOJI),
) -> StickerResponse:
    result = await db.execute(select(Sticker).where(Sticker.id == sticker_id))
    sticker = result.scalar_one_or_none()
    if sticker is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Sticker not found."}})
    sticker.name = body.name
    await db.commit()
    await dispatch(gw.sticker_update(sticker_id=sticker_id, name=body.name), db=db)
    return StickerResponse(sticker_id=sticker.id, name=sticker.name, creator_id=sticker.creator_id, image=sticker.image)


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
    # Clean up storage and file record
    if sticker.image:
        file_key = sticker.image.rsplit("/", 1)[-1]
        storage = get_storage()
        try:
            await storage.delete(file_key)
        except Exception:
            pass
        file_row = await db.get(File, file_key)
        if file_row:
            await db.delete(file_row)
    await db.delete(sticker)
    await db.commit()
    await dispatch(gw.sticker_delete(sticker_id=sticker_id), db=db)

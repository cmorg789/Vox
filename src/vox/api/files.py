"""File upload and download endpoints."""

import secrets
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


def _content_disposition(filename: str) -> str:
    """Build a safe Content-Disposition header value."""
    encoded = urllib.parse.quote(filename, safe=" ()-._~")
    return f"attachment; filename*=UTF-8''{encoded}"

import filetype
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse as FastAPIFileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Request as FastAPIRequest
from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Emoji, File, Message, Sticker, User, dm_participants, message_attachments
from vox.config import check_mime, config
from vox.models.files import FileResponse
from vox.permissions import ATTACH_FILES, MANAGE_MESSAGES, VIEW_SPACE, has_permission, resolve_permissions
from vox.storage import LocalStorage, get_storage

_UPLOAD_CHUNK_SIZE = 64 * 1024  # 64KB


async def _read_upload_chunked(file: UploadFile, max_bytes: int) -> bytes:
    """Read upload in chunks, aborting early if it exceeds max_bytes."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail={"error": {"code": "FILE_TOO_LARGE", "message": f"File exceeds {max_bytes} byte limit."}},
            )
        chunks.append(chunk)
    return b"".join(chunks)

router = APIRouter(tags=["files"])

UPLOAD_DIR = Path("uploads")


@router.post("/api/v1/feeds/{feed_id}/files", status_code=201)
async def upload_file(
    feed_id: int,
    file: UploadFile,
    name: str | None = Form(default=None),
    mime: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(ATTACH_FILES, space_type="feed", space_id_param="feed_id"),
) -> FileResponse:
    content = await _read_upload_chunked(file, config.limits.file_upload_max_bytes)

    file_id = secrets.token_urlsafe(16)
    file_name = name or file.filename or "upload"
    # Sniff MIME from content; fall back to client-supplied or application/octet-stream
    detected = filetype.guess(content)
    file_mime = detected.mime if detected else (mime or file.content_type or "application/octet-stream")

    if not check_mime(file_mime, config.media.allowed_file_mimes):
        raise HTTPException(
            status_code=415,
            detail={"error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": f"MIME type '{file_mime}' is not allowed."}},
        )

    storage = get_storage()
    url = await storage.put(file_id, content, file_mime)

    row = File(
        id=file_id,
        name=file_name,
        size=len(content),
        mime=file_mime,
        url=url,
        uploader_id=user.id,
        feed_id=feed_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    return FileResponse(file_id=file_id, name=file_name, size=len(content), mime=file_mime, url=row.url, uploader_id=user.id, created_at=int(row.created_at.timestamp()))


@router.post("/api/v1/dms/{dm_id}/files", status_code=201)
async def upload_dm_file(
    dm_id: int,
    file: UploadFile,
    name: str | None = Form(default=None),
    mime: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    from vox.api.dms import require_dm_participant, _dm_participant_ids
    # Verify user is DM participant
    pids = await _dm_participant_ids(db, dm_id)
    if user.id not in pids:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}},
        )

    content = await _read_upload_chunked(file, config.limits.file_upload_max_bytes)

    file_id = secrets.token_urlsafe(16)
    file_name = name or file.filename or "upload"
    # Sniff MIME from content; fall back to client-supplied or application/octet-stream
    detected = filetype.guess(content)
    file_mime = detected.mime if detected else (mime or file.content_type or "application/octet-stream")

    if not check_mime(file_mime, config.media.allowed_file_mimes):
        raise HTTPException(
            status_code=415,
            detail={"error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": f"MIME type '{file_mime}' is not allowed."}},
        )

    storage = get_storage()
    url = await storage.put(file_id, content, file_mime)

    row = File(
        id=file_id,
        name=file_name,
        size=len(content),
        mime=file_mime,
        url=url,
        uploader_id=user.id,
        dm_id=dm_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    return FileResponse(file_id=file_id, name=file_name, size=len(content), mime=file_mime, url=row.url, uploader_id=user.id, created_at=int(row.created_at.timestamp()))


@router.get("/api/v1/files/{file_id}")
async def download_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FILE_NOT_FOUND", "message": "File does not exist."}},
        )

    # Check access: find message this file is attached to
    msg_result = await db.execute(
        select(Message)
        .join(message_attachments, message_attachments.c.msg_id == Message.id)
        .where(message_attachments.c.file_id == file_id)
        .limit(1)
    )
    msg = msg_result.scalar_one_or_none()
    if msg:
        if msg.feed_id:
            resolved = await resolve_permissions(db, user.id, space_type="feed", space_id=msg.feed_id)
            if not has_permission(resolved, VIEW_SPACE):
                raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this file."}})
        elif msg.dm_id:
            is_participant = await db.scalar(
                select(func.count()).select_from(dm_participants)
                .where(dm_participants.c.dm_id == msg.dm_id, dm_participants.c.user_id == user.id)
            )
            if not is_participant:
                raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this file."}})
    elif row.uploader_id != user.id:
        # Check if the file is an emoji or sticker image (server-wide access)
        is_emoji = await db.scalar(
            select(func.count()).select_from(Emoji).where(Emoji.image == row.url)
        )
        is_sticker = not is_emoji and await db.scalar(
            select(func.count()).select_from(Sticker).where(Sticker.image == row.url)
        )
        if not is_emoji and not is_sticker:
            # Orphan file: only uploader can access
            raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this file."}})

    storage = get_storage()
    if not await storage.exists(file_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FILE_NOT_FOUND", "message": "File data missing."}},
        )

    # Always set Content-Disposition: attachment to prevent content-sniffing attacks
    disposition = _content_disposition(row.name)
    if isinstance(storage, LocalStorage):
        return FastAPIFileResponse(
            path=str(storage.local_path / file_id),
            media_type=row.mime,
            filename=row.name,
            headers={"Content-Disposition": disposition},
        )

    data = await storage.get(file_id)
    return Response(content=data, media_type=row.mime, headers={"Content-Disposition": disposition})


@router.delete("/api/v1/files/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FILE_NOT_FOUND", "message": "File does not exist."}},
        )
    # Only uploader or users with MANAGE_MESSAGES can delete
    if row.uploader_id != user.id:
        # Look up message context for permission resolution
        msg_result = await db.execute(
            select(Message)
            .join(message_attachments, message_attachments.c.msg_id == Message.id)
            .where(message_attachments.c.file_id == file_id)
            .limit(1)
        )
        msg = msg_result.scalar_one_or_none()
        if msg and msg.feed_id:
            resolved = await resolve_permissions(db, user.id, space_type="feed", space_id=msg.feed_id)
        else:
            resolved = await resolve_permissions(db, user.id)
        if not has_permission(resolved, MANAGE_MESSAGES):
            raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You can only delete your own files."}})
    storage = get_storage()
    await storage.delete(file_id)
    await db.delete(row)
    await db.commit()

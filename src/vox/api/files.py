"""File upload and download endpoints."""

import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse as FastAPIFileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import File, User
from vox.models.files import FileResponse
from vox.permissions import ATTACH_FILES

router = APIRouter(tags=["files"])

UPLOAD_DIR = Path("uploads")
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


@router.post("/api/v1/feeds/{feed_id}/files", status_code=201)
async def upload_file(
    feed_id: int,
    file: UploadFile,
    name: str | None = Form(default=None),
    mime: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(ATTACH_FILES, space_type="feed", space_id_param="feed_id"),
) -> FileResponse:
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail={"error": {"code": "FILE_TOO_LARGE", "message": f"File exceeds {MAX_FILE_SIZE} byte limit."}},
        )

    file_id = secrets.token_urlsafe(16)
    file_name = name or file.filename or "upload"
    file_mime = mime or file.content_type or "application/octet-stream"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / file_id
    dest.write_bytes(content)

    row = File(
        id=file_id,
        name=file_name,
        size=len(content),
        mime=file_mime,
        url=f"/api/v1/files/{file_id}",
        uploader_id=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    return FileResponse(file_id=file_id, name=file_name, size=len(content), mime=file_mime, url=row.url, uploader_id=user.id, created_at=int(row.created_at.timestamp()))


@router.get("/api/v1/files/{file_id}")
async def download_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FILE_NOT_FOUND", "message": "File does not exist."}},
        )

    path = UPLOAD_DIR / file_id
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FILE_NOT_FOUND", "message": "File data missing."}},
        )

    return FastAPIFileResponse(path=str(path), media_type=row.mime, filename=row.name)

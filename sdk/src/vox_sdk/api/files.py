"""Files API methods."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vox_sdk.models.files import FileResponse

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class FilesAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def upload(self, feed_id: int, file_path: str, filename: str, mime: str) -> FileResponse:
        data = await asyncio.to_thread(Path(file_path).read_bytes)
        r = await self._http.post(
            f"/api/v1/feeds/{feed_id}/files",
            files={"file": (filename, data, mime)},
        )
        return FileResponse.model_validate(r.json())

    async def upload_dm(self, dm_id: int, file_path: str, filename: str, mime: str) -> FileResponse:
        data = await asyncio.to_thread(Path(file_path).read_bytes)
        r = await self._http.post(
            f"/api/v1/dms/{dm_id}/files",
            files={"file": (filename, data, mime)},
        )
        return FileResponse.model_validate(r.json())

    async def upload_bytes(
        self, feed_id: int, data: bytes, filename: str, mime: str
    ) -> FileResponse:
        r = await self._http.post(
            f"/api/v1/feeds/{feed_id}/files",
            files={"file": (filename, data, mime)},
        )
        return FileResponse.model_validate(r.json())

    async def get(self, file_id: str) -> FileResponse:
        r = await self._http.get(f"/api/v1/files/{file_id}")
        return FileResponse.model_validate(r.json())

    async def delete(self, file_id: str) -> None:
        await self._http.delete(f"/api/v1/files/{file_id}")

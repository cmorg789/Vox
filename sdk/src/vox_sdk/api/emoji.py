"""Emoji & Sticker API methods."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vox_sdk.models.emoji import (
    EmojiListResponse,
    EmojiResponse,
    StickerListResponse,
    StickerResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class EmojiAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    # --- Emoji ---

    async def list_emoji(self) -> EmojiListResponse:
        r = await self._http.get("/api/v1/emoji")
        return EmojiListResponse.model_validate(r.json())

    async def create_emoji(self, name: str, image_path: str) -> EmojiResponse:
        data = await asyncio.to_thread(Path(image_path).read_bytes)
        r = await self._http.post(
            "/api/v1/emoji",
            data={"name": name},
            files={"image": data},
        )
        return EmojiResponse.model_validate(r.json())

    async def update_emoji(self, emoji_id: int, name: str) -> EmojiResponse:
        r = await self._http.patch(f"/api/v1/emoji/{emoji_id}", json={"name": name})
        return EmojiResponse.model_validate(r.json())

    async def delete_emoji(self, emoji_id: int) -> None:
        await self._http.delete(f"/api/v1/emoji/{emoji_id}")

    # --- Stickers ---

    async def list_stickers(self) -> StickerListResponse:
        r = await self._http.get("/api/v1/stickers")
        return StickerListResponse.model_validate(r.json())

    async def create_sticker(self, name: str, image_path: str) -> StickerResponse:
        data = await asyncio.to_thread(Path(image_path).read_bytes)
        r = await self._http.post(
            "/api/v1/stickers",
            data={"name": name},
            files={"image": data},
        )
        return StickerResponse.model_validate(r.json())

    async def update_sticker(self, sticker_id: int, name: str) -> StickerResponse:
        r = await self._http.patch(f"/api/v1/stickers/{sticker_id}", json={"name": name})
        return StickerResponse.model_validate(r.json())

    async def delete_sticker(self, sticker_id: int) -> None:
        await self._http.delete(f"/api/v1/stickers/{sticker_id}")

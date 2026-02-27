"""Response models for GIF proxy endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class GifMediaFormat(BaseModel):
    url: str
    width: int
    height: int


class GifResult(BaseModel):
    id: str
    title: str
    media_formats: dict[str, GifMediaFormat]


class GifSearchResponse(BaseModel):
    results: list[GifResult]
    next: str | None = None

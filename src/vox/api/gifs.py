"""GIF search proxy – keeps API keys server-side."""

from __future__ import annotations

import logging
from typing import Any, Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from vox.api.deps import get_current_user
from vox.config import config
from vox.db.models import User
from vox.models.gifs import GifMediaFormat, GifResult, GifSearchResponse

router = APIRouter(tags=["gifs"])
log = logging.getLogger(__name__)


def _require_api_key() -> str:
    key = config.gifs.api_key
    if not key:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "GIF_PROVIDER_UNAVAILABLE", "message": "GIF provider is not configured."}},
        )
    return key


# ---------------------------------------------------------------------------
# Klipy provider
# ---------------------------------------------------------------------------
_KLIPY_BASE = "https://api.klipy.com/api/v1"


def _klipy_search_url(api_key: str) -> str:
    return f"{_KLIPY_BASE}/{api_key}/gifs/search"


def _klipy_trending_url(api_key: str) -> str:
    return f"{_KLIPY_BASE}/{api_key}/gifs/trending"


def _klipy_params(limit: int, query: str | None = None) -> dict[str, str | int]:
    params: dict[str, str | int] = {"per_page": limit}
    if query:
        params["q"] = query
    if config.gifs.content_filter:
        params["content_filter"] = config.gifs.content_filter
    if config.gifs.locale:
        params["locale"] = config.gifs.locale
    return params


def _normalize_klipy(data: dict) -> GifSearchResponse:
    """Convert Klipy response into our normalized format."""
    inner = data.get("data", {})
    items = inner.get("data", [])
    results: list[GifResult] = []
    for item in items:
        file_info = item.get("file", {})
        media_formats: dict[str, GifMediaFormat] = {}
        for size_key, format_key in (("xs", "tinygif"), ("sm", "smallgif"), ("md", "gif"), ("hd", "hdgif")):
            variant = file_info.get(size_key, {})
            gif_fmt = variant.get("gif", {})
            if gif_fmt.get("url"):
                media_formats[format_key] = GifMediaFormat(
                    url=gif_fmt["url"],
                    width=gif_fmt.get("width", 0),
                    height=gif_fmt.get("height", 0),
                )
            mp4_fmt = variant.get("mp4", {})
            if mp4_fmt.get("url"):
                media_formats[f"{format_key}_mp4"] = GifMediaFormat(
                    url=mp4_fmt["url"],
                    width=mp4_fmt.get("width", 0),
                    height=mp4_fmt.get("height", 0),
                )
        results.append(GifResult(
            id=str(item.get("id", "")),
            title=item.get("title", ""),
            media_formats=media_formats,
        ))
    has_next = inner.get("has_next", False)
    page = inner.get("current_page", 1)
    return GifSearchResponse(
        results=results,
        next=str(page + 1) if has_next else None,
    )


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------
_Normalizer = Callable[[dict[str, Any]], GifSearchResponse]

_PROVIDERS: dict[str, dict[str, Any]] = {
    "klipy": {
        "search_url": _klipy_search_url,
        "trending_url": _klipy_trending_url,
        "params": _klipy_params,
        "normalize": _normalize_klipy,
    },
}


def _get_provider() -> dict[str, Any]:
    provider = _PROVIDERS.get(config.gifs.provider)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "GIF_PROVIDER_UNAVAILABLE", "message": f"Unknown GIF provider: {config.gifs.provider!r}"}},
        )
    return provider


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/gifs/search")
async def gif_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    _: User = Depends(get_current_user),
) -> GifSearchResponse:
    api_key = _require_api_key()
    prov = _get_provider()
    url = prov["search_url"](api_key)
    params = prov["params"](limit, query=q)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            return prov["normalize"](resp.json())
    except httpx.HTTPError:
        log.exception("GIF search upstream error")
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "GIF_UPSTREAM_ERROR", "message": "Failed to fetch GIFs from provider."}},
        )


@router.get("/api/v1/gifs/trending")
async def gif_trending(
    limit: int = Query(20, ge=1, le=50),
    _: User = Depends(get_current_user),
) -> GifSearchResponse:
    api_key = _require_api_key()
    prov = _get_provider()
    url = prov["trending_url"](api_key)
    params = prov["params"](limit)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            return prov["normalize"](resp.json())
    except httpx.HTTPError:
        log.exception("GIF trending upstream error")
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "GIF_UPSTREAM_ERROR", "message": "Failed to fetch GIFs from provider."}},
        )

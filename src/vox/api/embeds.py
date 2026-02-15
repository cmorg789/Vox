import re

import httpx
from fastapi import APIRouter, Depends

from vox.api.deps import get_current_user
from vox.db.models import User
from vox.models.messages import EmbedResponse, ResolveEmbedRequest

router = APIRouter(tags=["embeds"])

_MAX_RESPONSE_SIZE = 1 * 1024 * 1024  # 1MB


def _extract_meta(html: str) -> dict[str, str | None]:
    """Extract OpenGraph and fallback meta tags from HTML."""
    result: dict[str, str | None] = {
        "title": None,
        "description": None,
        "image": None,
        "video": None,
    }

    # OpenGraph tags
    og_pattern = re.compile(
        r'<meta\s+[^>]*property=["\']og:(\w+)["\'][^>]*content=["\']([^"\']*)["\']',
        re.IGNORECASE,
    )
    # Also match reversed attribute order: content before property
    og_pattern_rev = re.compile(
        r'<meta\s+[^>]*content=["\']([^"\']*)["\'][^>]*property=["\']og:(\w+)["\']',
        re.IGNORECASE,
    )

    for match in og_pattern.finditer(html):
        key = match.group(1).lower()
        if key in result:
            result[key] = match.group(2)

    for match in og_pattern_rev.finditer(html):
        key = match.group(2).lower()
        if key in result and result[key] is None:
            result[key] = match.group(1)

    # Fallback: <title>
    if result["title"] is None:
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            result["title"] = title_match.group(1).strip()

    # Fallback: <meta name="description">
    if result["description"] is None:
        desc_pattern = re.compile(
            r'<meta\s+[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        desc_match = desc_pattern.search(html)
        if desc_match:
            result["description"] = desc_match.group(1)

    return result


@router.post("/api/v1/embeds/resolve")
async def resolve_embed(
    body: ResolveEmbedRequest,
    _: User = Depends(get_current_user),
) -> EmbedResponse:
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(body.url, timeout=5.0, headers={"User-Agent": "VoxBot/1.0"})
            if len(resp.content) > _MAX_RESPONSE_SIZE:
                return EmbedResponse()
            html = resp.text
    except (httpx.HTTPError, Exception):
        return EmbedResponse()

    meta = _extract_meta(html)
    return EmbedResponse(
        title=meta["title"],
        description=meta["description"],
        image=meta["image"],
        video=meta["video"],
    )

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException

from vox.api.deps import get_current_user
from vox.db.models import User
from vox.models.bots import Embed
from vox.models.messages import ResolveEmbedRequest

router = APIRouter(tags=["embeds"])

_MAX_RESPONSE_SIZE = 1 * 1024 * 1024  # 1MB
_ALLOWED_SCHEMES = {"http", "https"}


def _validate_url(url: str) -> str:
    """Validate URL to prevent SSRF: reject private/loopback/link-local IPs."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_URL", "message": "Only http and https URLs are allowed."}},
        )
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_URL", "message": "URL must contain a hostname."}},
        )
    try:
        addrinfos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_URL", "message": "Could not resolve hostname."}},
        )
    for family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_URL", "message": "URLs pointing to private/internal addresses are not allowed."}},
            )
    return url


def _extract_meta(html: str) -> dict[str, str | None]:
    """Extract OpenGraph and fallback meta tags from HTML."""
    result: dict[str, str | None] = {
        "title": None,
        "description": None,
        "image": None,
        "video": None,
        "site_name": None,
        "type": None,
        "locale": None,
        "audio": None,
        "url": None,
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
) -> Embed:
    _validate_url(body.url)
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.get(body.url, timeout=5.0, headers={"User-Agent": "VoxBot/1.0"})
            # Follow redirects manually, validating each target
            redirects = 0
            while resp.is_redirect and redirects < 5:
                location = resp.headers.get("location")
                if not location:
                    break
                _validate_url(location)
                resp = await client.get(location, timeout=5.0, headers={"User-Agent": "VoxBot/1.0"})
                redirects += 1
            if len(resp.content) > _MAX_RESPONSE_SIZE:
                return Embed()
            html = resp.text
    except httpx.HTTPError:
        return Embed()

    meta = _extract_meta(html)
    return Embed(
        title=meta["title"],
        description=meta["description"],
        image=meta["image"],
        video=meta["video"],
        site_name=meta["site_name"],
        type=meta["type"],
        locale=meta["locale"],
        audio=meta["audio"],
        url=meta["url"],
    )

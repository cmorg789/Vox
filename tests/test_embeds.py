import socket
from unittest.mock import AsyncMock, patch

import httpx


async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _public_addrinfo(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0))]


async def test_resolve_embed_og_tags(client):
    h = await setup(client)

    html = """
    <html><head>
        <meta property="og:title" content="Test Page">
        <meta property="og:description" content="A test description">
        <meta property="og:image" content="https://example.com/img.png">
        <meta property="og:video" content="https://example.com/vid.mp4">
    </head><body></body></html>
    """

    mock_response = httpx.Response(200, text=html, request=httpx.Request("GET", "https://example.com"))

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Test Page"
    assert data["description"] == "A test description"
    assert data["image"] == "https://example.com/img.png"
    assert data["video"] == "https://example.com/vid.mp4"


async def test_resolve_embed_fallback_title(client):
    h = await setup(client)

    html = """
    <html><head>
        <title>Fallback Title</title>
        <meta name="description" content="Fallback desc">
    </head><body></body></html>
    """

    mock_response = httpx.Response(200, text=html, request=httpx.Request("GET", "https://example.com"))

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Fallback Title"
    assert data["description"] == "Fallback desc"


async def test_resolve_embed_fetch_failure(client):
    h = await setup(client)

    def fake_getaddrinfo(host, port, *a, **kw):
        return [(2, 1, 6, '', ('93.184.216.34', 0))]

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_client_cls, \
         patch("vox.api.embeds.socket.getaddrinfo", fake_getaddrinfo):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://nonexistent.example"})

    assert r.status_code == 200
    data = r.json()
    assert data["title"] is None
    assert data["description"] is None
    assert data["image"] is None
    assert data["video"] is None


async def test_resolve_embed_no_auth(client):
    r = await client.post("/api/v1/embeds/resolve", json={"url": "https://example.com"})
    assert r.status_code in (401, 403, 422)


async def test_resolve_embed_og_takes_precedence(client):
    """OG tags should take precedence over fallback title/description."""
    h = await setup(client)

    html = """
    <html><head>
        <title>Fallback</title>
        <meta name="description" content="Fallback desc">
        <meta property="og:title" content="OG Title">
        <meta property="og:description" content="OG Desc">
    </head><body></body></html>
    """

    mock_response = httpx.Response(200, text=html, request=httpx.Request("GET", "https://example.com"))

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    data = r.json()
    assert data["title"] == "OG Title"
    assert data["description"] == "OG Desc"


async def test_resolve_embed_invalid_scheme(client):
    """Reject URLs with non-http(s) schemes."""
    h = await setup(client)
    with patch("vox.api.embeds.socket.getaddrinfo", _public_addrinfo):
        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "ftp://example.com/file"})
    assert r.status_code == 400
    assert "INVALID_URL" in r.text


async def test_resolve_embed_no_hostname(client):
    """Reject URLs with no hostname."""
    h = await setup(client)
    r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://"})
    assert r.status_code == 400
    assert "INVALID_URL" in r.text


async def test_resolve_embed_dns_failure(client):
    """Reject URLs whose hostname cannot be resolved."""
    h = await setup(client)
    with patch("vox.api.embeds.socket.getaddrinfo", side_effect=socket.gaierror("Name resolution failed")):
        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://nonexistent.invalid"})
    assert r.status_code == 400
    assert "INVALID_URL" in r.text


async def test_resolve_embed_private_ip(client):
    """Reject URLs that resolve to private/internal IPs (SSRF protection)."""
    h = await setup(client)

    def private_addrinfo(host, port, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 0))]

    with patch("vox.api.embeds.socket.getaddrinfo", private_addrinfo):
        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://evil.example.com"})
    assert r.status_code == 400
    assert "INVALID_URL" in r.text


async def test_resolve_embed_reversed_og_tags(client):
    """OG tags with content before property attribute should be parsed."""
    h = await setup(client)

    html = '<html><head><meta content="Rev Title" property="og:title"><meta content="Rev Desc" property="og:description"></head></html>'
    mock_response = httpx.Response(200, text=html, request=httpx.Request("GET", "https://example.com"))

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    data = r.json()
    assert data["title"] == "Rev Title"
    assert data["description"] == "Rev Desc"


async def test_resolve_embed_redirect_ssrf(client):
    """Redirects to private IPs should be blocked (redirect SSRF)."""
    h = await setup(client)

    redirect_resp = httpx.Response(
        302, headers={"location": "https://internal.local/secret"},
        request=httpx.Request("GET", "https://example.com"),
    )

    def addrinfo_for(host, port, *a, **kw):
        if host == "internal.local":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0))]

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_cls, \
         patch("vox.api.embeds.socket.getaddrinfo", addrinfo_for):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=redirect_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    # The HTTPException from _validate_url now properly propagates as a 400
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_URL"


async def test_resolve_embed_redirect_followed(client):
    """Valid redirects should be followed and content extracted."""
    h = await setup(client)

    redirect_resp = httpx.Response(
        302, headers={"location": "https://final.example.com/page"},
        request=httpx.Request("GET", "https://example.com"),
    )
    final_html = '<html><head><title>Final Page</title></head></html>'
    final_resp = httpx.Response(200, text=final_html, request=httpx.Request("GET", "https://final.example.com/page"))

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_cls, \
         patch("vox.api.embeds.socket.getaddrinfo", _public_addrinfo):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[redirect_resp, final_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    data = r.json()
    assert data["title"] == "Final Page"


async def test_resolve_embed_redirect_no_location(client):
    """Redirect with no location header should stop following."""
    h = await setup(client)

    redirect_resp = httpx.Response(
        302, headers={},
        request=httpx.Request("GET", "https://example.com"),
    )
    redirect_resp._content = b"<html><head><title>Stopped</title></head></html>"

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_cls, \
         patch("vox.api.embeds.socket.getaddrinfo", _public_addrinfo):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=redirect_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    assert r.status_code == 200


async def test_resolve_embed_response_too_large(client):
    """Responses over 1MB should return empty embed."""
    h = await setup(client)

    big_content = b"x" * (1024 * 1024 + 1)
    mock_response = httpx.Response(200, content=big_content, request=httpx.Request("GET", "https://example.com"))

    with patch("vox.api.embeds.httpx.AsyncClient") as mock_cls, \
         patch("vox.api.embeds.socket.getaddrinfo", _public_addrinfo):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        r = await client.post("/api/v1/embeds/resolve", headers=h, json={"url": "https://example.com"})

    data = r.json()
    assert data["title"] is None
    assert data["description"] is None

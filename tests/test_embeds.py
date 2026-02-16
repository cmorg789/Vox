from unittest.mock import AsyncMock, patch

import httpx


async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


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

"""Unit tests for the Client class."""

from __future__ import annotations

import json

import httpx
import pytest

from vox_sdk.client import Client
from vox_sdk.api.messages import MessagesAPI
from vox_sdk.api.channels import ChannelsAPI
from vox_sdk.api.members import MembersAPI
from vox_sdk.api.roles import RolesAPI
from vox_sdk.api.server import ServerAPI
from vox_sdk.api.users import UsersAPI
from vox_sdk.api.invites import InvitesAPI
from vox_sdk.api.voice import VoiceAPI
from vox_sdk.api.dms import DMsAPI
from vox_sdk.api.webhooks import WebhooksAPI
from vox_sdk.api.bots import BotsAPI
from vox_sdk.api.e2ee import E2EEAPI
from vox_sdk.api.moderation import ModerationAPI
from vox_sdk.api.files import FilesAPI
from vox_sdk.api.federation import FederationAPI
from vox_sdk.api.search import SearchAPI
from vox_sdk.api.emoji import EmojiAPI
from vox_sdk.api.sync import SyncAPI


class TestLazyAPIProperties:
    def test_lazy_api_properties(self):
        """Each API property returns the correct type and is cached."""
        client = Client("https://vox.test")

        expected = {
            "messages": MessagesAPI,
            "channels": ChannelsAPI,
            "members": MembersAPI,
            "roles": RolesAPI,
            "server": ServerAPI,
            "users": UsersAPI,
            "invites": InvitesAPI,
            "voice": VoiceAPI,
            "dms": DMsAPI,
            "webhooks": WebhooksAPI,
            "bots": BotsAPI,
            "e2ee": E2EEAPI,
            "moderation": ModerationAPI,
            "files": FilesAPI,
            "federation": FederationAPI,
            "search": SearchAPI,
            "emoji": EmojiAPI,
            "sync": SyncAPI,
        }

        for prop_name, expected_type in expected.items():
            first = getattr(client, prop_name)
            assert isinstance(first, expected_type), f"{prop_name} should be {expected_type.__name__}"
            second = getattr(client, prop_name)
            assert first is second, f"{prop_name} should be cached (same object)"


class TestContextManager:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """async with Client(...) enters and exits cleanly."""
        async with Client("https://vox.test") as client:
            assert client is not None
            assert client.http is not None
        # After exit, the HTTP client should be closed
        assert client.http._client.is_closed


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_stores_token(self, mock_transport):
        """login() sets http.token on success."""
        transport, calls = mock_transport
        transport.response = httpx.Response(
            200,
            json={"token": "tok-abc", "user_id": 1, "display_name": "Alice", "roles": []},
        )

        client = Client("https://vox.test")
        client.http._client = httpx.AsyncClient(
            base_url="https://vox.test", transport=transport,
        )

        result = await client.login("alice", "password123")
        assert client.http.token == "tok-abc"
        assert result.token == "tok-abc"
        await client.close()

    @pytest.mark.asyncio
    async def test_login_mfa_does_not_store_token(self, mock_transport):
        """When MFA is required, token is NOT set."""
        transport, calls = mock_transport
        transport.response = httpx.Response(
            200,
            json={
                "mfa_required": True,
                "mfa_ticket": "ticket-xyz",
                "available_methods": ["totp"],
            },
        )

        client = Client("https://vox.test")
        client.http._client = httpx.AsyncClient(
            base_url="https://vox.test", transport=transport,
        )

        result = await client.login("alice", "password123")
        assert client.http.token is None
        assert result.mfa_ticket == "ticket-xyz"
        await client.close()


class TestLoginErrors:
    @pytest.mark.asyncio
    async def test_login_error_propagates(self, mock_transport):
        """A 401 from login raises VoxHTTPError and token stays None."""
        from vox_sdk.errors import VoxHTTPError

        transport, calls = mock_transport
        transport.response = httpx.Response(
            401,
            json={"error": {"code": "AUTH_FAILED", "message": "Invalid credentials."}},
        )

        client = Client("https://vox.test")
        client.http._client = httpx.AsyncClient(
            base_url="https://vox.test", transport=transport,
        )

        with pytest.raises(VoxHTTPError) as exc_info:
            await client.login("alice", "wrong")
        assert exc_info.value.status == 401
        assert client.http.token is None
        await client.close()


class TestCloseClient:
    @pytest.mark.asyncio
    async def test_close_without_gateway(self):
        """Close works cleanly when no gateway is connected."""
        client = Client("https://vox.test")
        assert client._gateway is None
        await client.close()
        assert client.http._client.is_closed

    @pytest.mark.asyncio
    async def test_close_with_gateway(self):
        """Close calls close() on both gateway and http."""
        from unittest.mock import AsyncMock
        client = Client("https://vox.test")
        mock_gw = AsyncMock()
        client._gateway = mock_gw
        await client.close()
        mock_gw.close.assert_awaited_once()
        assert client.http._client.is_closed


class TestTokenPropagation:
    @pytest.mark.asyncio
    async def test_token_propagates_to_api_groups(self, mock_transport):
        """API groups use the client's HTTP client (and thus its token)."""
        transport, calls = mock_transport
        transport.response = httpx.Response(200, json={
            "token": "tok-abc", "user_id": 1, "display_name": "Alice", "roles": [],
        })

        client = Client("https://vox.test")
        client.http._client = httpx.AsyncClient(
            base_url="https://vox.test", transport=transport,
        )

        await client.login("alice", "password123")
        # Token should be set
        assert client.http.token == "tok-abc"

        # API groups should share the same HTTP client
        assert client.messages._http is client.http
        assert client.channels._http is client.http
        assert client.roles._http is client.http
        await client.close()


class TestConstructorTimeout:
    def test_timeout_reaches_inner_client(self):
        """Timeout parameter is forwarded to the httpx client."""
        client = Client("https://vox.test", timeout=5.0)
        assert client.http._client.timeout.connect == 5.0
        assert client.http._client.timeout.read == 5.0


class TestConnectGateway:
    @pytest.mark.asyncio
    async def test_connect_gateway_requires_login(self):
        """Calling connect_gateway() without token raises RuntimeError."""
        client = Client("https://vox.test")
        with pytest.raises(RuntimeError, match="Must be logged in"):
            await client.connect_gateway()
        await client.close()

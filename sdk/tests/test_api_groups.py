"""Unit tests for all 18 API groups — verifies correct URLs, methods, payloads, and return types."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# --- Messages API ---

class TestMessagesAPI:
    @pytest.mark.asyncio
    async def test_list_default_params(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"messages": []})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        result = await api.list(10)
        assert calls[0]["method"] == "GET"
        assert calls[0]["path"] == "/api/v1/feeds/10/messages"
        assert "limit=50" in calls[0]["url"]

    @pytest.mark.asyncio
    async def test_list_with_before_and_after(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"messages": []})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.list(5, before=100, after=50, limit=25)
        assert "before=100" in calls[0]["url"]
        assert "after=50" in calls[0]["url"]
        assert "limit=25" in calls[0]["url"]

    @pytest.mark.asyncio
    async def test_get(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "msg_id": 42, "feed_id": 1, "author_id": 1, "body": "hi",
            "timestamp": 1000, "attachments": [],
        })
        from vox_sdk.api.messages import MessagesAPI
        from vox_sdk.models.messages import MessageResponse
        api = MessagesAPI(client)
        result = await api.get(1, 42)
        assert calls[0]["path"] == "/api/v1/feeds/1/messages/42"
        assert isinstance(result, MessageResponse)
        assert result.msg_id == 42

    @pytest.mark.asyncio
    async def test_send_minimal(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"msg_id": 1, "timestamp": 1000})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.send(10, "hello")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/feeds/10/messages"
        assert calls[0]["body"] == {"body": "hello"}

    @pytest.mark.asyncio
    async def test_send_full_payload(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"msg_id": 1, "timestamp": 1000})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.send(10, "hi", reply_to=5, attachments=["f1"], mentions=[1, 2], embed="e")
        body = calls[0]["body"]
        assert body["reply_to"] == 5
        assert body["attachments"] == ["f1"]
        assert body["mentions"] == [1, 2]
        assert body["embed"] == "e"

    @pytest.mark.asyncio
    async def test_send_no_body(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"msg_id": 1, "timestamp": 1000})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.send(10, attachments=["f1"])
        assert "body" not in calls[0]["body"]

    @pytest.mark.asyncio
    async def test_edit(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"msg_id": 1, "edit_timestamp": 2000})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.edit(10, 1, "updated")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/feeds/10/messages/1"
        assert calls[0]["body"] == {"body": "updated"}

    @pytest.mark.asyncio
    async def test_delete(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.delete(10, 1)
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/feeds/10/messages/1"

    @pytest.mark.asyncio
    async def test_bulk_delete(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.bulk_delete(10, [1, 2, 3])
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/feeds/10/messages/bulk-delete"
        assert calls[0]["body"] == {"msg_ids": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_list_thread(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"messages": []})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.list_thread(10, 5, before=100, limit=25)
        assert calls[0]["path"] == "/api/v1/feeds/10/threads/5/messages"
        assert "before=100" in calls[0]["url"]

    @pytest.mark.asyncio
    async def test_send_thread(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"msg_id": 1, "timestamp": 1000})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.send_thread(10, 5, "hello")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/feeds/10/threads/5/messages"

    @pytest.mark.asyncio
    async def test_add_reaction(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.add_reaction(10, 1, "thumbsup")
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/feeds/10/messages/1/reactions/thumbsup"

    @pytest.mark.asyncio
    async def test_remove_reaction(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.remove_reaction(10, 1, "thumbsup")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/feeds/10/messages/1/reactions/thumbsup"

    @pytest.mark.asyncio
    async def test_pin(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.pin(10, 1)
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/feeds/10/pins/1"

    @pytest.mark.asyncio
    async def test_unpin(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.unpin(10, 1)
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/feeds/10/pins/1"

    @pytest.mark.asyncio
    async def test_list_pins(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"messages": []})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.list_pins(10)
        assert calls[0]["method"] == "GET"
        assert calls[0]["path"] == "/api/v1/feeds/10/pins"

    @pytest.mark.asyncio
    async def test_list_reactions(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"reactions": []})
        from vox_sdk.api.messages import MessagesAPI
        api = MessagesAPI(client)
        await api.list_reactions(10, 1)
        assert calls[0]["path"] == "/api/v1/feeds/10/messages/1/reactions"


# --- Channels API ---

class TestChannelsAPI:
    @pytest.mark.asyncio
    async def test_get_feed(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "feed_id": 1, "name": "general", "type": "text",
        })
        from vox_sdk.api.channels import ChannelsAPI
        from vox_sdk.models.channels import FeedResponse
        api = ChannelsAPI(client)
        result = await api.get_feed(1)
        assert calls[0]["path"] == "/api/v1/feeds/1"
        assert isinstance(result, FeedResponse)

    @pytest.mark.asyncio
    async def test_create_feed_minimal(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "feed_id": 2, "name": "news", "type": "text",
        })
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.create_feed("news")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/feeds"
        assert calls[0]["body"] == {"name": "news", "type": "text"}

    @pytest.mark.asyncio
    async def test_create_feed_with_category_and_overrides(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "feed_id": 2, "name": "news", "type": "text", "category_id": 5,
        })
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        overrides = [{"target_type": "role", "target_id": 1, "allow": 8, "deny": 0}]
        await api.create_feed("news", category_id=5, permission_overrides=overrides)
        body = calls[0]["body"]
        assert body["category_id"] == 5
        assert body["permission_overrides"] == overrides

    @pytest.mark.asyncio
    async def test_update_feed(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "feed_id": 1, "name": "renamed", "type": "text", "topic": "new topic",
        })
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.update_feed(1, name="renamed", topic="new topic")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["body"] == {"name": "renamed", "topic": "new topic"}

    @pytest.mark.asyncio
    async def test_delete_feed(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.delete_feed(1)
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/feeds/1"

    @pytest.mark.asyncio
    async def test_create_room(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "room_id": 1, "name": "lounge", "type": "voice",
        })
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.create_room("lounge")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/rooms"
        assert calls[0]["body"]["name"] == "lounge"

    @pytest.mark.asyncio
    async def test_list_categories(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"items": [], "cursor": None})
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.list_categories()
        assert calls[0]["path"] == "/api/v1/categories"

    @pytest.mark.asyncio
    async def test_create_category(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "category_id": 1, "name": "Gaming", "position": 0,
        })
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.create_category("Gaming", position=2)
        assert calls[0]["body"] == {"name": "Gaming", "position": 2}

    @pytest.mark.asyncio
    async def test_create_thread(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "thread_id": 1, "parent_feed_id": 10, "parent_msg_id": 5, "name": "discussion",
        })
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.create_thread(10, 5, "discussion")
        assert calls[0]["path"] == "/api/v1/feeds/10/threads"
        assert calls[0]["body"] == {"parent_msg_id": 5, "name": "discussion"}

    @pytest.mark.asyncio
    async def test_subscribe_feed(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.subscribe_feed(10)
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/feeds/10/subscribers"

    @pytest.mark.asyncio
    async def test_update_thread(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "thread_id": 1, "parent_feed_id": 10, "parent_msg_id": 5, "name": "updated",
        })
        from vox_sdk.api.channels import ChannelsAPI
        api = ChannelsAPI(client)
        await api.update_thread(1, name="updated", archived=True, locked=True)
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/threads/1"
        assert calls[0]["body"] == {"name": "updated", "archived": True, "locked": True}


# --- Auth API ---

class TestAuthAPI:
    @pytest.mark.asyncio
    async def test_register(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(201, json={"user_id": 1, "token": "abc"})
        from vox_sdk.api.auth import AuthAPI
        from vox_sdk.models.auth import RegisterResponse
        api = AuthAPI(client)
        result = await api.register("alice", "pass123")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/auth/register"
        assert calls[0]["body"] == {"username": "alice", "password": "pass123"}
        assert isinstance(result, RegisterResponse)

    @pytest.mark.asyncio
    async def test_register_with_display_name(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(201, json={"user_id": 1, "token": "abc"})
        from vox_sdk.api.auth import AuthAPI
        api = AuthAPI(client)
        await api.register("alice", "pass123", display_name="Alice W")
        assert calls[0]["body"]["display_name"] == "Alice W"

    @pytest.mark.asyncio
    async def test_login_success(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "token": "tok-1", "user_id": 1, "display_name": "Alice", "roles": [],
        })
        from vox_sdk.api.auth import AuthAPI
        from vox_sdk.models.auth import LoginResponse
        api = AuthAPI(client)
        result = await api.login("alice", "pass")
        assert isinstance(result, LoginResponse)
        assert result.token == "tok-1"

    @pytest.mark.asyncio
    async def test_login_mfa_required(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "mfa_required": True, "mfa_ticket": "ticket-1", "available_methods": ["totp"],
        })
        from vox_sdk.api.auth import AuthAPI
        from vox_sdk.models.auth import MFARequiredResponse
        api = AuthAPI(client)
        result = await api.login("alice", "pass")
        assert isinstance(result, MFARequiredResponse)
        assert result.mfa_ticket == "ticket-1"

    @pytest.mark.asyncio
    async def test_login_2fa(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "token": "tok-2", "user_id": 1, "display_name": "Alice", "roles": [],
        })
        from vox_sdk.api.auth import AuthAPI
        api = AuthAPI(client)
        await api.login_2fa("ticket-1", "totp", code="123456")
        assert calls[0]["path"] == "/api/v1/auth/login/2fa"
        assert calls[0]["body"]["mfa_ticket"] == "ticket-1"
        assert calls[0]["body"]["code"] == "123456"

    @pytest.mark.asyncio
    async def test_logout(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.auth import AuthAPI
        api = AuthAPI(client)
        await api.logout()
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/auth/logout"

    @pytest.mark.asyncio
    async def test_mfa_setup(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "setup_id": "s1", "method": "totp",
        })
        from vox_sdk.api.auth import AuthAPI
        api = AuthAPI(client)
        await api.mfa_setup("totp")
        assert calls[0]["path"] == "/api/v1/auth/2fa/setup"
        assert calls[0]["body"]["method"] == "totp"

    @pytest.mark.asyncio
    async def test_mfa_remove(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"success": True})
        from vox_sdk.api.auth import AuthAPI
        api = AuthAPI(client)
        await api.mfa_remove("totp", code="123456")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/auth/2fa"
        assert calls[0]["body"]["method"] == "totp"


# --- Members API ---

class TestMembersAPI:
    @pytest.mark.asyncio
    async def test_list(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "items": [{"user_id": 1, "display_name": "Alice", "role_ids": []}], "cursor": None,
        })
        from vox_sdk.api.members import MembersAPI
        api = MembersAPI(client)
        result = await api.list()
        assert calls[0]["path"] == "/api/v1/members"

    @pytest.mark.asyncio
    async def test_get(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_id": 42, "display_name": "Bob", "role_ids": [],
        })
        from vox_sdk.api.members import MembersAPI
        from vox_sdk.models.members import MemberResponse
        api = MembersAPI(client)
        result = await api.get(42)
        assert calls[0]["path"] == "/api/v1/members/42"
        assert isinstance(result, MemberResponse)

    @pytest.mark.asyncio
    async def test_join(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.members import MembersAPI
        api = MembersAPI(client)
        await api.join("abc123")
        assert calls[0]["method"] == "POST"
        assert calls[0]["body"] == {"invite_code": "abc123"}

    @pytest.mark.asyncio
    async def test_ban_with_reason(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_id": 5, "display_name": "Bad", "reason": "spam",
        })
        from vox_sdk.api.members import MembersAPI
        api = MembersAPI(client)
        await api.ban(5, reason="spam", delete_msg_days=7)
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/bans/5"
        assert calls[0]["body"]["reason"] == "spam"
        assert calls[0]["body"]["delete_msg_days"] == 7

    @pytest.mark.asyncio
    async def test_update_nickname(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_id": 1, "display_name": "Alice", "nickname": "Ali", "role_ids": [],
        })
        from vox_sdk.api.members import MembersAPI
        api = MembersAPI(client)
        await api.update(1, nickname="Ali")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/members/1"
        assert calls[0]["body"] == {"nickname": "Ali"}


# --- Roles API ---

class TestRolesAPI:
    @pytest.mark.asyncio
    async def test_list(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"items": [], "cursor": None})
        from vox_sdk.api.roles import RolesAPI
        api = RolesAPI(client)
        await api.list()
        assert calls[0]["path"] == "/api/v1/roles"

    @pytest.mark.asyncio
    async def test_create(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "role_id": 1, "name": "Mod", "permissions": 8, "position": 1,
        })
        from vox_sdk.api.roles import RolesAPI
        api = RolesAPI(client)
        await api.create("Mod", color=0xFF0000, permissions=8, position=1)
        body = calls[0]["body"]
        assert body["name"] == "Mod"
        assert body["color"] == 0xFF0000
        assert body["permissions"] == 8

    @pytest.mark.asyncio
    async def test_assign(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.roles import RolesAPI
        api = RolesAPI(client)
        await api.assign(user_id=1, role_id=5)
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/members/1/roles/5"

    @pytest.mark.asyncio
    async def test_revoke(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.roles import RolesAPI
        api = RolesAPI(client)
        await api.revoke(user_id=1, role_id=5)
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/members/1/roles/5"

    @pytest.mark.asyncio
    async def test_set_feed_override(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.roles import RolesAPI
        api = RolesAPI(client)
        await api.set_feed_override(10, "role", 5, allow=8, deny=2)
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/feeds/10/permissions/role/5"
        assert calls[0]["body"] == {"allow": 8, "deny": 2}

    @pytest.mark.asyncio
    async def test_set_room_override(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.roles import RolesAPI
        api = RolesAPI(client)
        await api.set_room_override(20, "member", 3, allow=4, deny=1)
        assert calls[0]["path"] == "/api/v1/rooms/20/permissions/member/3"


# --- Server API ---

class TestServerAPI:
    @pytest.mark.asyncio
    async def test_info(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "name": "My Server", "member_count": 10,
        })
        from vox_sdk.api.server import ServerAPI
        from vox_sdk.models.server import ServerInfoResponse
        api = ServerAPI(client)
        result = await api.info()
        assert calls[0]["path"] == "/api/v1/server"
        assert isinstance(result, ServerInfoResponse)
        assert result.name == "My Server"

    @pytest.mark.asyncio
    async def test_update(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"name": "Updated", "member_count": 10})
        from vox_sdk.api.server import ServerAPI
        api = ServerAPI(client)
        await api.update(name="Updated", description="A server")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["body"]["name"] == "Updated"
        assert calls[0]["body"]["description"] == "A server"

    @pytest.mark.asyncio
    async def test_layout(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "categories": [], "feeds": [], "rooms": [],
        })
        from vox_sdk.api.server import ServerAPI
        api = ServerAPI(client)
        await api.layout()
        assert calls[0]["path"] == "/api/v1/server/layout"

    @pytest.mark.asyncio
    async def test_gateway_info(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "url": "wss://gw.vox.test", "media_url": "wss://media.vox.test",
            "protocol_version": 1, "min_version": 1, "max_version": 1,
        })
        from vox_sdk.api.server import ServerAPI
        from vox_sdk.models.server import GatewayInfoResponse
        api = ServerAPI(client)
        result = await api.gateway_info()
        assert calls[0]["path"] == "/api/v1/gateway"
        assert isinstance(result, GatewayInfoResponse)

    @pytest.mark.asyncio
    async def test_get_limits(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"max_members": 500})
        from vox_sdk.api.server import ServerAPI
        api = ServerAPI(client)
        result = await api.get_limits()
        assert calls[0]["path"] == "/api/v1/server/limits"
        assert result == {"max_members": 500}

    @pytest.mark.asyncio
    async def test_update_limits(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"max_members": 1000})
        from vox_sdk.api.server import ServerAPI
        api = ServerAPI(client)
        result = await api.update_limits(max_members=1000)
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/server/limits"
        assert calls[0]["body"] == {"limits": {"max_members": 1000}}


# --- Users API ---

class TestUsersAPI:
    @pytest.mark.asyncio
    async def test_get(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_id": 1, "username": "alice", "display_name": "Alice",
        })
        from vox_sdk.api.users import UsersAPI
        from vox_sdk.models.users import UserResponse
        api = UsersAPI(client)
        result = await api.get(1)
        assert calls[0]["path"] == "/api/v1/users/1"
        assert isinstance(result, UserResponse)

    @pytest.mark.asyncio
    async def test_update_profile(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_id": 1, "username": "alice", "display_name": "Alice Updated",
        })
        from vox_sdk.api.users import UsersAPI
        api = UsersAPI(client)
        await api.update_profile(1, display_name="Alice Updated", bio="Hello")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/users/1"
        assert calls[0]["body"] == {"display_name": "Alice Updated", "bio": "Hello"}

    @pytest.mark.asyncio
    async def test_list_friends(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"items": [], "cursor": None})
        from vox_sdk.api.users import UsersAPI
        api = UsersAPI(client)
        await api.list_friends(1)
        assert calls[0]["path"] == "/api/v1/users/1/friends"

    @pytest.mark.asyncio
    async def test_list_blocks(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"blocked_user_ids": []})
        from vox_sdk.api.users import UsersAPI
        api = UsersAPI(client)
        await api.list_blocks(1)
        assert calls[0]["path"] == "/api/v1/users/1/blocks"

    @pytest.mark.asyncio
    async def test_get_dm_settings(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"dm_permission": "everyone"})
        from vox_sdk.api.users import UsersAPI
        from vox_sdk.models.users import DMSettingsResponse
        api = UsersAPI(client)
        result = await api.get_dm_settings(1)
        assert calls[0]["path"] == "/api/v1/users/1/dm-settings"
        assert isinstance(result, DMSettingsResponse)


# --- DMs API ---

class TestDMsAPI:
    @pytest.mark.asyncio
    async def test_open_1to1(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "dm_id": 1, "participant_ids": [1, 2], "is_group": False,
        })
        from vox_sdk.api.dms import DMsAPI
        api = DMsAPI(client)
        await api.open(recipient_id=2)
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/dms"
        assert calls[0]["body"] == {"recipient_id": 2}

    @pytest.mark.asyncio
    async def test_open_group(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "dm_id": 2, "participant_ids": [1, 2, 3], "is_group": True, "name": "Group",
        })
        from vox_sdk.api.dms import DMsAPI
        api = DMsAPI(client)
        await api.open(recipient_ids=[2, 3], name="Group")
        body = calls[0]["body"]
        assert body["recipient_ids"] == [2, 3]
        assert body["name"] == "Group"

    @pytest.mark.asyncio
    async def test_send_message(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"msg_id": 1, "timestamp": 1000})
        from vox_sdk.api.dms import DMsAPI
        api = DMsAPI(client)
        await api.send_message(1, "hello")
        assert calls[0]["path"] == "/api/v1/dms/1/messages"
        assert calls[0]["body"] == {"body": "hello"}

    @pytest.mark.asyncio
    async def test_list_messages(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"messages": []})
        from vox_sdk.api.dms import DMsAPI
        api = DMsAPI(client)
        await api.list_messages(1, before=100, limit=25)
        assert calls[0]["path"] == "/api/v1/dms/1/messages"
        assert "before=100" in calls[0]["url"]

    @pytest.mark.asyncio
    async def test_close(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.dms import DMsAPI
        api = DMsAPI(client)
        await api.close(1)
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/dms/1"

    @pytest.mark.asyncio
    async def test_send_read_receipt(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.dms import DMsAPI
        api = DMsAPI(client)
        await api.send_read_receipt(1, up_to_msg_id=50)
        assert calls[0]["path"] == "/api/v1/dms/1/read"
        assert calls[0]["body"] == {"up_to_msg_id": 50}


# --- Voice API ---

class TestVoiceAPI:
    @pytest.mark.asyncio
    async def test_join(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "media_url": "wss://media.test", "media_token": "mt", "members": [],
        })
        from vox_sdk.api.voice import VoiceAPI
        from vox_sdk.models.voice import VoiceJoinResponse
        api = VoiceAPI(client)
        result = await api.join(10, self_mute=True)
        assert calls[0]["path"] == "/api/v1/rooms/10/voice/join"
        assert calls[0]["body"]["self_mute"] is True
        assert isinstance(result, VoiceJoinResponse)

    @pytest.mark.asyncio
    async def test_leave(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.voice import VoiceAPI
        api = VoiceAPI(client)
        await api.leave(10)
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/rooms/10/voice/leave"

    @pytest.mark.asyncio
    async def test_server_mute(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.voice import VoiceAPI
        api = VoiceAPI(client)
        await api.server_mute(10, user_id=5, muted=True)
        assert calls[0]["path"] == "/api/v1/rooms/10/voice/mute"
        assert calls[0]["body"] == {"user_id": 5, "muted": True}

    @pytest.mark.asyncio
    async def test_get_media_cert_success(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "fingerprint": "sha256:abcd1234",
            "cert_der": [48, 130, 1, 0],
        })
        from vox_sdk.api.voice import VoiceAPI
        from vox_sdk.models.voice import MediaCertResponse
        api = VoiceAPI(client)
        result = await api.get_media_cert()
        assert calls[0]["path"] == "/api/v1/voice/media-cert"
        assert calls[0]["method"] == "GET"
        assert isinstance(result, MediaCertResponse)
        assert result.fingerprint == "sha256:abcd1234"
        assert result.cert_der == [48, 130, 1, 0]

    @pytest.mark.asyncio
    async def test_get_media_cert_no_pinning(self, http_client):
        """404 with NO_CERT_PINNING returns None (CA-signed mode)."""
        client, transport, calls = http_client
        transport.response = httpx.Response(
            404,
            json={"error": {"code": "NO_CERT_PINNING", "message": "CA-signed certificate in use"}},
        )
        from vox_sdk.api.voice import VoiceAPI
        api = VoiceAPI(client)
        result = await api.get_media_cert()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_media_cert_unexpected_error(self, http_client):
        """Other errors are re-raised."""
        client, transport, calls = http_client
        transport.response = httpx.Response(
            500, json={"error": {"code": "VALIDATION_ERROR", "message": "boom"}},
        )
        from vox_sdk.api.voice import VoiceAPI
        from vox_sdk.errors import VoxHTTPError
        api = VoiceAPI(client)
        with pytest.raises(VoxHTTPError) as exc_info:
            await api.get_media_cert()
        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_stage_set_topic(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"topic": "AMA"})
        from vox_sdk.api.voice import VoiceAPI
        from vox_sdk.models.voice import StageTopicResponse
        api = VoiceAPI(client)
        result = await api.stage_set_topic(10, "AMA")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/rooms/10/stage/topic"
        assert isinstance(result, StageTopicResponse)


# --- Invites API ---

class TestInvitesAPI:
    @pytest.mark.asyncio
    async def test_create_with_options(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "code": "abc", "creator_id": 1,
        })
        from vox_sdk.api.invites import InvitesAPI
        api = InvitesAPI(client)
        await api.create(feed_id=10, max_uses=5, max_age=3600)
        body = calls[0]["body"]
        assert body["feed_id"] == 10
        assert body["max_uses"] == 5
        assert body["max_age"] == 3600

    @pytest.mark.asyncio
    async def test_delete(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.invites import InvitesAPI
        api = InvitesAPI(client)
        await api.delete("abc")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/invites/abc"

    @pytest.mark.asyncio
    async def test_resolve(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "code": "abc", "server_name": "Test", "member_count": 10,
        })
        from vox_sdk.api.invites import InvitesAPI
        from vox_sdk.models.invites import InvitePreviewResponse
        api = InvitesAPI(client)
        result = await api.resolve("abc")
        assert calls[0]["path"] == "/api/v1/invites/abc"
        assert isinstance(result, InvitePreviewResponse)


# --- Webhooks API ---

class TestWebhooksAPI:
    @pytest.mark.asyncio
    async def test_create(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "webhook_id": 1, "feed_id": 10, "name": "Bot", "token": "wh-tok",
        })
        from vox_sdk.api.webhooks import WebhooksAPI
        from vox_sdk.models.bots import WebhookResponse
        api = WebhooksAPI(client)
        result = await api.create(10, "Bot")
        assert calls[0]["path"] == "/api/v1/feeds/10/webhooks"
        assert isinstance(result, WebhookResponse)

    @pytest.mark.asyncio
    async def test_list(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"webhooks": []})
        from vox_sdk.api.webhooks import WebhooksAPI
        api = WebhooksAPI(client)
        await api.list(10)
        assert calls[0]["path"] == "/api/v1/feeds/10/webhooks"

    @pytest.mark.asyncio
    async def test_update(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "webhook_id": 1, "feed_id": 10, "name": "Updated",
        })
        from vox_sdk.api.webhooks import WebhooksAPI
        api = WebhooksAPI(client)
        await api.update(1, name="Updated")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/webhooks/1"

    @pytest.mark.asyncio
    async def test_execute_with_embeds(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.webhooks import WebhooksAPI
        from vox_sdk.models.bots import Embed
        api = WebhooksAPI(client)
        embed = Embed(title="Alert", description="Something happened")
        await api.execute(1, "wh-tok", "hello", embeds=[embed])
        assert calls[0]["path"] == "/api/v1/webhooks/1/wh-tok"
        body = calls[0]["body"]
        assert body["body"] == "hello"
        assert len(body["embeds"]) == 1
        assert body["embeds"][0]["title"] == "Alert"


# --- Bots API ---

class TestBotsAPI:
    @pytest.mark.asyncio
    async def test_register_commands(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"ok": True})
        from vox_sdk.api.bots import BotsAPI
        api = BotsAPI(client)
        cmds = [{"name": "ping", "description": "Pong!"}]
        await api.register_commands(1, cmds)
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/bots/1/commands"
        assert calls[0]["body"]["commands"] == cmds

    @pytest.mark.asyncio
    async def test_respond_to_interaction(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.bots import BotsAPI
        api = BotsAPI(client)
        await api.respond_to_interaction("int-1", body="Pong!", ephemeral=True)
        assert calls[0]["path"] == "/api/v1/interactions/int-1/response"
        assert calls[0]["body"]["body"] == "Pong!"
        assert calls[0]["body"]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_component_interaction(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.bots import BotsAPI
        api = BotsAPI(client)
        await api.component_interaction(msg_id=42, component_id="btn-1")
        assert calls[0]["path"] == "/api/v1/interactions/component"
        assert calls[0]["body"] == {"msg_id": 42, "component_id": "btn-1"}

    @pytest.mark.asyncio
    async def test_list_commands(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"commands": []})
        from vox_sdk.api.bots import BotsAPI
        api = BotsAPI(client)
        await api.list_commands()
        assert calls[0]["path"] == "/api/v1/commands"


# --- Files API ---

class TestFilesAPI:
    @pytest.mark.asyncio
    async def test_upload_bytes(self):
        """upload_bytes sends a multipart POST to the correct path."""
        upload_calls: list[dict] = []

        class MultipartTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                # For multipart, read the stream
                await request.aread()
                upload_calls.append({
                    "method": request.method,
                    "path": request.url.path,
                })
                return httpx.Response(200, json={
                    "file_id": "f1", "name": "test.png", "size": 100, "mime": "image/png",
                    "url": "https://cdn.test/f1",
                })

        from vox_sdk.http import HTTPClient
        from vox_sdk.api.files import FilesAPI
        from vox_sdk.models.files import FileResponse
        client = HTTPClient("https://vox.test", token="test-token")
        client._client = httpx.AsyncClient(base_url="https://vox.test", transport=MultipartTransport())
        api = FilesAPI(client)
        result = await api.upload_bytes(10, b"\x89PNG", "test.png", "image/png")
        assert upload_calls[0]["method"] == "POST"
        assert upload_calls[0]["path"] == "/api/v1/feeds/10/files"
        assert isinstance(result, FileResponse)
        await client.close()

    @pytest.mark.asyncio
    async def test_get(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "file_id": "f1", "name": "test.png", "size": 100, "mime": "image/png",
            "url": "https://cdn.test/f1",
        })
        from vox_sdk.api.files import FilesAPI
        api = FilesAPI(client)
        await api.get("f1")
        assert calls[0]["path"] == "/api/v1/files/f1"

    @pytest.mark.asyncio
    async def test_delete(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.files import FilesAPI
        api = FilesAPI(client)
        await api.delete("f1")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/files/f1"


# --- E2EE API ---

class TestE2EEAPI:
    @pytest.mark.asyncio
    async def test_upload_prekeys(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.e2ee import E2EEAPI
        api = E2EEAPI(client)
        await api.upload_prekeys("dev-1", "ik", "spk", ["otk1", "otk2"])
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/api/v1/keys/prekeys/dev-1"
        assert calls[0]["body"]["identity_key"] == "ik"

    @pytest.mark.asyncio
    async def test_get_prekeys(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_id": 1, "devices": [],
        })
        from vox_sdk.api.e2ee import E2EEAPI
        from vox_sdk.models.e2ee import PrekeyBundleResponse
        api = E2EEAPI(client)
        result = await api.get_prekeys(1)
        assert calls[0]["path"] == "/api/v1/keys/prekeys/1"
        assert isinstance(result, PrekeyBundleResponse)

    @pytest.mark.asyncio
    async def test_add_device(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"device_id": "dev-1"})
        from vox_sdk.api.e2ee import E2EEAPI
        api = E2EEAPI(client)
        await api.add_device("dev-1", "Phone")
        assert calls[0]["path"] == "/api/v1/keys/devices"
        assert calls[0]["body"] == {"device_id": "dev-1", "device_name": "Phone"}


# --- Moderation API ---

class TestModerationAPI:
    @pytest.mark.asyncio
    async def test_create_report(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "report_id": 1, "reporter_id": 1, "reported_user_id": 5,
            "reason": "spam", "status": "open",
        })
        from vox_sdk.api.moderation import ModerationAPI
        from vox_sdk.models.moderation import ReportResponse
        api = ModerationAPI(client)
        result = await api.create_report(5, "spam", feed_id=10, msg_id=42)
        assert calls[0]["path"] == "/api/v1/reports"
        body = calls[0]["body"]
        assert body["reported_user_id"] == 5
        assert body["feed_id"] == 10
        assert isinstance(result, ReportResponse)

    @pytest.mark.asyncio
    async def test_audit_log_params(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"entries": [], "cursor": None})
        from vox_sdk.api.moderation import ModerationAPI
        api = ModerationAPI(client)
        await api.audit_log(event_type="ban", actor_id=1)
        assert calls[0]["path"] == "/api/v1/audit-log"
        assert "event_type=ban" in calls[0]["url"]
        assert "actor_id=1" in calls[0]["url"]

    @pytest.mark.asyncio
    async def test_resolve_report(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.moderation import ModerationAPI
        api = ModerationAPI(client)
        await api.resolve_report(1, "warn")
        assert calls[0]["path"] == "/api/v1/reports/1/resolve"
        assert calls[0]["body"] == {"action": "warn"}


# --- Federation API ---

class TestFederationAPI:
    @pytest.mark.asyncio
    async def test_get_prekeys(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_address": "alice@remote.test", "devices": [],
        })
        from vox_sdk.api.federation import FederationAPI
        from vox_sdk.models.federation import FederatedPrekeyResponse
        api = FederationAPI(client)
        result = await api.get_prekeys("alice@remote.test")
        assert calls[0]["path"] == "/api/v1/federation/users/alice@remote.test/prekeys"
        assert isinstance(result, FederatedPrekeyResponse)

    @pytest.mark.asyncio
    async def test_join_request(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "accepted": True, "federation_token": "ft-1",
        })
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.join_request("remote.test", invite_code="abc")
        assert calls[0]["path"] == "/api/v1/federation/join-request"
        assert calls[0]["body"]["invite_code"] == "abc"

    @pytest.mark.asyncio
    async def test_admin_block(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={})
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.admin_block("bad.test", reason="abuse")
        assert calls[0]["path"] == "/api/v1/federation/admin/block"
        assert calls[0]["body"] == {"domain": "bad.test", "reason": "abuse"}

    @pytest.mark.asyncio
    async def test_admin_unblock(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204)
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.admin_unblock("bad.test")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/federation/admin/block/bad.test"

    @pytest.mark.asyncio
    async def test_admin_block_list(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "items": [{"domain": "evil.test", "reason": "spam", "created_at": "2025-01-01T00:00:00"}],
        })
        from vox_sdk.api.federation import FederationAPI
        from vox_sdk.models.federation import FederationEntryListResponse
        api = FederationAPI(client)
        result = await api.admin_block_list()
        assert calls[0]["path"] == "/api/v1/federation/admin/block"
        assert isinstance(result, FederationEntryListResponse)
        assert len(result.items) == 1
        assert result.items[0].domain == "evil.test"

    @pytest.mark.asyncio
    async def test_admin_allow(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204)
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.admin_allow("friend.test", reason="trusted")
        assert calls[0]["path"] == "/api/v1/federation/admin/allow"
        assert calls[0]["body"] == {"domain": "friend.test", "reason": "trusted"}

    @pytest.mark.asyncio
    async def test_admin_allow_no_reason(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204)
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.admin_allow("friend.test")
        assert calls[0]["body"] == {"domain": "friend.test"}

    @pytest.mark.asyncio
    async def test_admin_unallow(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204)
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.admin_unallow("friend.test")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/federation/admin/allow/friend.test"

    @pytest.mark.asyncio
    async def test_admin_allow_list(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "items": [{"domain": "friend.test", "reason": "trusted", "created_at": "2025-01-01T00:00:00"}],
        })
        from vox_sdk.api.federation import FederationAPI
        from vox_sdk.models.federation import FederationEntryListResponse
        api = FederationAPI(client)
        result = await api.admin_allow_list()
        assert calls[0]["path"] == "/api/v1/federation/admin/allow"
        assert isinstance(result, FederationEntryListResponse)
        assert len(result.items) == 1
        assert result.items[0].domain == "friend.test"


# --- Search API ---

class TestSearchAPI:
    @pytest.mark.asyncio
    async def test_messages_with_params(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"results": []})
        from vox_sdk.api.search import SearchAPI
        api = SearchAPI(client)
        await api.messages(q="hello", feed_id=10, limit=25)
        assert calls[0]["path"] == "/api/v1/messages/search"
        assert "q=hello" in calls[0]["url"]
        assert "feed_id=10" in calls[0]["url"]


# --- Sync API ---

class TestSyncAPI:
    @pytest.mark.asyncio
    async def test_sync_minimal(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "events": [], "server_timestamp": 1000,
        })
        from vox_sdk.api.sync import SyncAPI
        from vox_sdk.models.sync import SyncResponse
        api = SyncAPI(client)
        result = await api.sync(1000)
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/sync"
        assert calls[0]["body"]["since_timestamp"] == 1000
        assert isinstance(result, SyncResponse)

    @pytest.mark.asyncio
    async def test_sync_with_categories_and_after(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "events": [], "server_timestamp": 2000,
        })
        from vox_sdk.api.sync import SyncAPI
        api = SyncAPI(client)
        await api.sync(1000, categories=["messages", "members"], limit=50, after=500)
        body = calls[0]["body"]
        assert body["categories"] == ["messages", "members"]
        assert body["limit"] == 50
        assert body["after"] == 500


# --- Emoji API ---

class TestEmojiAPI:
    @pytest.mark.asyncio
    async def test_list_emoji(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={"items": [], "cursor": None})
        from vox_sdk.api.emoji import EmojiAPI
        api = EmojiAPI(client)
        await api.list_emoji()
        assert calls[0]["path"] == "/api/v1/emoji"

    @pytest.mark.asyncio
    async def test_update_emoji(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "emoji_id": 1, "name": "renamed", "creator_id": 1,
        })
        from vox_sdk.api.emoji import EmojiAPI
        api = EmojiAPI(client)
        await api.update_emoji(1, "renamed")
        assert calls[0]["method"] == "PATCH"
        assert calls[0]["path"] == "/api/v1/emoji/1"
        assert calls[0]["body"] == {"name": "renamed"}

    @pytest.mark.asyncio
    async def test_delete_emoji(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(204, json={})
        from vox_sdk.api.emoji import EmojiAPI
        api = EmojiAPI(client)
        await api.delete_emoji(1)
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/emoji/1"


# --- Embeds API ---

class TestEmbedsAPI:
    @pytest.mark.asyncio
    async def test_resolve(self, http_client):
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "title": "Example", "description": "An example page",
            "url": "https://example.com",
        })
        from vox_sdk.api.embeds import EmbedsAPI
        from vox_sdk.models.bots import Embed
        api = EmbedsAPI(client)
        result = await api.resolve("https://example.com")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/embeds/resolve"
        assert calls[0]["body"] == {"url": "https://example.com"}
        assert isinstance(result, Embed)
        assert result.title == "Example"


# --- Async file upload tests ---

class TestAsyncFileUpload:
    @pytest.mark.asyncio
    async def test_upload_uses_to_thread(self, http_client, monkeypatch, tmp_path):
        """upload() reads file bytes via asyncio.to_thread."""
        client, transport, calls = http_client
        import asyncio

        # Create a temp file
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"hello world")

        # Track that to_thread was called
        thread_calls = []
        original_to_thread = asyncio.to_thread

        async def tracking_to_thread(func, *args):
            thread_calls.append(func)
            return await original_to_thread(func, *args)

        monkeypatch.setattr(asyncio, "to_thread", tracking_to_thread)

        # Need a transport that handles multipart
        class MultipartTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                await request.aread()
                return httpx.Response(200, json={
                    "file_id": "f1", "name": "test.txt", "size": 11,
                    "mime": "text/plain", "url": "https://cdn.test/f1",
                })

        client._client = httpx.AsyncClient(base_url="https://vox.test", transport=MultipartTransport())

        from vox_sdk.api.files import FilesAPI
        api = FilesAPI(client)
        result = await api.upload(10, str(test_file), "test.txt", "text/plain")
        assert len(thread_calls) == 1
        assert result.file_id == "f1"

    @pytest.mark.asyncio
    async def test_upload_dm_uses_to_thread(self, http_client, monkeypatch, tmp_path):
        """upload_dm() reads file bytes via asyncio.to_thread."""
        client, transport, calls = http_client
        import asyncio

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"hello")

        thread_calls = []
        original_to_thread = asyncio.to_thread

        async def tracking_to_thread(func, *args):
            thread_calls.append(func)
            return await original_to_thread(func, *args)

        monkeypatch.setattr(asyncio, "to_thread", tracking_to_thread)

        class MultipartTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                await request.aread()
                return httpx.Response(200, json={
                    "file_id": "f2", "name": "test.txt", "size": 5,
                    "mime": "text/plain", "url": "https://cdn.test/f2",
                })

        client._client = httpx.AsyncClient(base_url="https://vox.test", transport=MultipartTransport())

        from vox_sdk.api.files import FilesAPI
        api = FilesAPI(client)
        result = await api.upload_dm(1, str(test_file), "test.txt", "text/plain")
        assert len(thread_calls) == 1
        assert result.file_id == "f2"

    @pytest.mark.asyncio
    async def test_create_emoji_uses_to_thread(self, http_client, monkeypatch, tmp_path):
        """create_emoji() reads image via asyncio.to_thread."""
        client, transport, calls = http_client
        import asyncio

        test_file = tmp_path / "emoji.png"
        test_file.write_bytes(b"\x89PNG")

        thread_calls = []
        original_to_thread = asyncio.to_thread

        async def tracking_to_thread(func, *args):
            thread_calls.append(func)
            return await original_to_thread(func, *args)

        monkeypatch.setattr(asyncio, "to_thread", tracking_to_thread)

        class MultipartTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                await request.aread()
                return httpx.Response(200, json={
                    "emoji_id": 1, "name": "fire", "creator_id": 1,
                })

        client._client = httpx.AsyncClient(base_url="https://vox.test", transport=MultipartTransport())

        from vox_sdk.api.emoji import EmojiAPI
        api = EmojiAPI(client)
        result = await api.create_emoji("fire", str(test_file))
        assert len(thread_calls) == 1
        assert result.emoji_id == 1


# --- Federation URL encoding test ---

class TestFederationURLEncoding:
    @pytest.mark.asyncio
    async def test_user_address_encoded(self, http_client):
        """User address with special chars is URL-encoded, preserving @."""
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_address": "alice@remote.test", "devices": [],
        })
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.get_prekeys("alice@remote.test")
        # @ should be preserved
        assert "@" in calls[0]["path"]
        assert calls[0]["path"] == "/api/v1/federation/users/alice@remote.test/prekeys"

    @pytest.mark.asyncio
    async def test_user_address_with_special_chars(self, http_client):
        """User address with path-unsafe chars gets encoded."""
        client, transport, calls = http_client
        transport.response = httpx.Response(200, json={
            "user_address": "user name@remote.test", "display_name": "User",
        })
        from vox_sdk.api.federation import FederationAPI
        api = FederationAPI(client)
        await api.get_profile("user name@remote.test")
        # Space should be encoded as %20 in the URL
        assert "user%20name@remote.test" in calls[0]["url"]

"""Integration tests for SDK federation admin allow/block list methods."""

import pytest

from vox_sdk.models.federation import FederationEntryListResponse

from .conftest import make_sdk_client, register


@pytest.mark.asyncio
class TestFederationAdminAllow:
    async def test_add_list_remove(self, sdk):
        await register(sdk, "admin", "password123")

        await sdk.federation.admin_allow("friend.example", reason="trusted")

        result = await sdk.federation.admin_allow_list()
        assert isinstance(result, FederationEntryListResponse)
        assert len(result.items) == 1
        assert result.items[0].domain == "friend.example"
        assert result.items[0].reason == "trusted"

        await sdk.federation.admin_unallow("friend.example")

        result = await sdk.federation.admin_allow_list()
        assert len(result.items) == 0

    async def test_idempotent_add(self, sdk):
        await register(sdk, "admin", "password123")

        await sdk.federation.admin_allow("dup.example")
        await sdk.federation.admin_allow("dup.example")

        result = await sdk.federation.admin_allow_list()
        assert len(result.items) == 1

    async def test_idempotent_remove(self, sdk):
        await register(sdk, "admin", "password123")
        # Should not raise even if entry doesn't exist
        await sdk.federation.admin_unallow("nonexistent.example")

    async def test_requires_admin(self, app, db):
        sdk1 = await make_sdk_client(app)
        sdk2 = await make_sdk_client(app)
        try:
            await register(sdk1, "admin_user", "password123")
            await register(sdk2, "regular_user", "password123")

            from vox_sdk.errors import VoxHTTPError
            with pytest.raises(VoxHTTPError) as exc_info:
                await sdk2.federation.admin_allow("x.example")
            assert exc_info.value.status == 403
        finally:
            await sdk1.close()
            await sdk2.close()


@pytest.mark.asyncio
class TestFederationAdminBlock:
    async def test_list_and_unblock(self, sdk):
        await register(sdk, "admin", "password123")

        await sdk.federation.admin_block("evil.example", reason="spam")

        result = await sdk.federation.admin_block_list()
        assert isinstance(result, FederationEntryListResponse)
        assert len(result.items) == 1
        assert result.items[0].domain == "evil.example"

        await sdk.federation.admin_unblock("evil.example")

        result = await sdk.federation.admin_block_list()
        assert len(result.items) == 0

    async def test_unblock_idempotent(self, sdk):
        await register(sdk, "admin", "password123")
        await sdk.federation.admin_unblock("nonexistent.example")

    async def test_no_cross_contamination(self, sdk):
        await register(sdk, "admin", "password123")

        await sdk.federation.admin_allow("allowed.example")
        await sdk.federation.admin_block("blocked.example")

        blocks = await sdk.federation.admin_block_list()
        block_domains = [i.domain for i in blocks.items]
        assert "blocked.example" in block_domains
        assert "allowed.example" not in block_domains

        allows = await sdk.federation.admin_allow_list()
        allow_domains = [i.domain for i in allows.items]
        assert "allowed.example" in allow_domains
        assert "blocked.example" not in allow_domains

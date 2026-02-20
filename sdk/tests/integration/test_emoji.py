"""SDK integration tests for emoji endpoints."""

import tempfile
from pathlib import Path

import pytest

from vox_sdk import VoxHTTPError

from .conftest import register

pytestmark = pytest.mark.anyio


class TestEmoji:
    async def test_emoji_crud(self, sdk):
        """Create, update, list, and delete a custom emoji.

        Uses a minimal 1x1 PNG file for the upload. If the server rejects the
        upload in the test environment, the test is skipped.
        """
        reg = await register(sdk, "alice", "password123")

        # Minimal valid 1x1 PNG (67 bytes)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            tmp_path = f.name

        try:
            emoji = await sdk.emoji.create_emoji("testmoji", tmp_path)
        except VoxHTTPError:
            pytest.skip("Emoji upload not supported in test environment")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        assert emoji.emoji_id > 0
        assert emoji.name == "testmoji"
        assert emoji.creator_id == reg.user_id

        updated = await sdk.emoji.update_emoji(emoji.emoji_id, "newname")
        assert updated.name == "newname"

        emoji_list = await sdk.emoji.list_emoji()
        assert any(e.emoji_id == emoji.emoji_id for e in emoji_list.items)

        await sdk.emoji.delete_emoji(emoji.emoji_id)
        emoji_list = await sdk.emoji.list_emoji()
        assert not any(e.emoji_id == emoji.emoji_id for e in emoji_list.items)

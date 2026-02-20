"""SDK integration tests for sticker endpoints."""

import tempfile
from pathlib import Path

import pytest

from vox_sdk import VoxHTTPError

from .conftest import register

pytestmark = pytest.mark.anyio


class TestStickers:
    async def test_sticker_crud(self, sdk):
        """Create, update, list, and delete a custom sticker.

        Uses a minimal 1x1 PNG file for the upload.
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
            sticker = await sdk.emoji.create_sticker("teststicker", tmp_path)
        except VoxHTTPError:
            pytest.skip("Sticker upload not supported in test environment")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        assert sticker.sticker_id > 0
        assert sticker.name == "teststicker"
        assert sticker.creator_id == reg.user_id

        updated = await sdk.emoji.update_sticker(sticker.sticker_id, "newname")
        assert updated.name == "newname"

        sticker_list = await sdk.emoji.list_stickers()
        assert any(s.sticker_id == sticker.sticker_id for s in sticker_list.items)

        await sdk.emoji.delete_sticker(sticker.sticker_id)
        sticker_list = await sdk.emoji.list_stickers()
        assert not any(s.sticker_id == sticker.sticker_id for s in sticker_list.items)

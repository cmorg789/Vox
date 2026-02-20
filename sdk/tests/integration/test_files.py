"""SDK integration tests for file endpoints."""

import tempfile
from pathlib import Path

import pytest

from vox_sdk import VoxHTTPError

from .conftest import register

pytestmark = pytest.mark.anyio


class TestFiles:
    async def test_upload_and_delete(self, sdk):
        reg = await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("uploads")

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            tmp_path = f.name

        try:
            uploaded = await sdk.files.upload(
                feed.feed_id, tmp_path, "test.txt", "text/plain"
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        assert uploaded.file_id
        assert uploaded.name == "test.txt"
        assert uploaded.size == 11
        assert uploaded.mime == "text/plain"
        assert uploaded.uploader_id == reg.user_id

        # Delete the file
        await sdk.files.delete(uploaded.file_id)

        # Verify 404
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.files.delete(uploaded.file_id)
        assert exc_info.value.status == 404

    async def test_upload_bytes(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("uploads")

        uploaded = await sdk.files.upload_bytes(
            feed.feed_id, b"hello from bytes", "data.txt", "text/plain"
        )
        assert uploaded.file_id
        assert uploaded.name == "data.txt"
        assert uploaded.size == 16
        assert uploaded.mime == "text/plain"

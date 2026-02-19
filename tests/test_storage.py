"""Tests for the pluggable storage backends."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# LocalStorage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_storage_get(tmp_path):
    from vox.storage import LocalStorage

    store = LocalStorage(str(tmp_path / "uploads"))
    url = await store.put("key1", b"hello", "text/plain")
    assert url == "/api/v1/files/key1"
    data = await store.get("key1")
    assert data == b"hello"


@pytest.mark.asyncio
async def test_local_storage_delete(tmp_path):
    from vox.storage import LocalStorage

    store = LocalStorage(str(tmp_path / "uploads"))
    await store.put("key2", b"data", "text/plain")
    assert await store.exists("key2") is True
    await store.delete("key2")
    assert await store.exists("key2") is False


@pytest.mark.asyncio
async def test_local_storage_delete_nonexistent(tmp_path):
    from vox.storage import LocalStorage

    store = LocalStorage(str(tmp_path / "uploads"))
    await store.delete("nope")  # should not raise


@pytest.mark.asyncio
async def test_local_storage_exists(tmp_path):
    from vox.storage import LocalStorage

    store = LocalStorage(str(tmp_path / "uploads"))
    assert await store.exists("missing") is False
    await store.put("present", b"x", "text/plain")
    assert await store.exists("present") is True


# ---------------------------------------------------------------------------
# S3Storage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s3_storage_init_missing_aioboto3():
    import vox.storage as mod

    with patch.dict("sys.modules", {"aioboto3": None}):
        # Force the import inside __init__ to fail
        with patch("builtins.__import__", side_effect=ImportError("no aioboto3")):
            with pytest.raises(RuntimeError, match="aioboto3 is required"):
                mod.S3Storage(bucket="test")


def test_s3_storage_session_kwargs():
    from vox.storage import S3Storage

    with patch("builtins.__import__", return_value=MagicMock()):
        s3 = object.__new__(S3Storage)
        s3.bucket = "b"
        s3.endpoint = "https://endpoint"
        s3.access_key = "ak"
        s3.secret_key = "sk"
        s3.region = "us-west-2"
        s3.public_url = None

        kwargs = s3._session_kwargs()
        assert kwargs["endpoint_url"] == "https://endpoint"
        assert kwargs["aws_access_key_id"] == "ak"
        assert kwargs["aws_secret_access_key"] == "sk"
        assert kwargs["region_name"] == "us-west-2"

    # Without endpoint
    with patch("builtins.__import__", return_value=MagicMock()):
        s3b = object.__new__(S3Storage)
        s3b.bucket = "b"
        s3b.endpoint = None
        s3b.access_key = None
        s3b.secret_key = None
        s3b.region = "us-east-1"
        s3b.public_url = None

        kwargs2 = s3b._session_kwargs()
        assert "endpoint_url" not in kwargs2
        assert "aws_access_key_id" not in kwargs2


@pytest.mark.asyncio
async def test_s3_storage_put_with_public_url():
    mock_s3_client = AsyncMock()
    mock_s3_client.put_object = AsyncMock()

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_ctx

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    from vox.storage import S3Storage

    s3 = object.__new__(S3Storage)
    s3.bucket = "mybucket"
    s3.endpoint = None
    s3.access_key = None
    s3.secret_key = None
    s3.region = "us-east-1"
    s3.public_url = "https://cdn.example.com"

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
        url = await s3.put("file123", b"content", "image/png")

    assert url == "https://cdn.example.com/file123"
    mock_s3_client.put_object.assert_awaited_once()


@pytest.mark.asyncio
async def test_s3_storage_put_without_public_url():
    mock_s3_client = AsyncMock()
    mock_s3_client.put_object = AsyncMock()

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_ctx

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    from vox.storage import S3Storage

    s3 = object.__new__(S3Storage)
    s3.bucket = "mybucket"
    s3.endpoint = None
    s3.access_key = None
    s3.secret_key = None
    s3.region = "us-east-1"
    s3.public_url = None

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
        url = await s3.put("file456", b"content", "image/png")

    assert url == "/api/v1/files/file456"


@pytest.mark.asyncio
async def test_s3_storage_get():
    mock_body = AsyncMock()
    mock_body.read = AsyncMock(return_value=b"filedata")

    mock_s3_client = AsyncMock()
    mock_s3_client.get_object = AsyncMock(return_value={"Body": mock_body})

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_ctx

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    from vox.storage import S3Storage

    s3 = object.__new__(S3Storage)
    s3.bucket = "mybucket"
    s3.endpoint = None
    s3.access_key = None
    s3.secret_key = None
    s3.region = "us-east-1"
    s3.public_url = None

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
        data = await s3.get("key1")

    assert data == b"filedata"


@pytest.mark.asyncio
async def test_s3_storage_delete():
    mock_s3_client = AsyncMock()
    mock_s3_client.delete_object = AsyncMock()

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_ctx

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    from vox.storage import S3Storage

    s3 = object.__new__(S3Storage)
    s3.bucket = "mybucket"
    s3.endpoint = None
    s3.access_key = None
    s3.secret_key = None
    s3.region = "us-east-1"
    s3.public_url = None

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3}):
        await s3.delete("key1")

    mock_s3_client.delete_object.assert_awaited_once_with(Bucket="mybucket", Key="key1")


@pytest.mark.asyncio
async def test_s3_storage_exists_true_and_false():
    # True case
    mock_s3_client_true = AsyncMock()
    mock_s3_client_true.head_object = AsyncMock(return_value={})

    mock_ctx_true = AsyncMock()
    mock_ctx_true.__aenter__ = AsyncMock(return_value=mock_s3_client_true)
    mock_ctx_true.__aexit__ = AsyncMock(return_value=False)

    mock_session_true = MagicMock()
    mock_session_true.client.return_value = mock_ctx_true

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session_true

    # Mock botocore.exceptions.ClientError
    mock_botocore_exc = MagicMock()

    class FakeClientError(Exception):
        pass

    mock_botocore_exc.ClientError = FakeClientError

    from vox.storage import S3Storage

    s3 = object.__new__(S3Storage)
    s3.bucket = "mybucket"
    s3.endpoint = None
    s3.access_key = None
    s3.secret_key = None
    s3.region = "us-east-1"
    s3.public_url = None

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3, "botocore.exceptions": mock_botocore_exc, "botocore": MagicMock()}):
        result = await s3.exists("key1")
    assert result is True

    # False case — head_object raises ClientError
    mock_s3_client_false = AsyncMock()
    mock_s3_client_false.head_object = AsyncMock(side_effect=FakeClientError("not found"))

    mock_ctx_false = AsyncMock()
    mock_ctx_false.__aenter__ = AsyncMock(return_value=mock_s3_client_false)
    mock_ctx_false.__aexit__ = AsyncMock(return_value=False)

    mock_session_false = MagicMock()
    mock_session_false.client.return_value = mock_ctx_false
    mock_aioboto3.Session.return_value = mock_session_false

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3, "botocore.exceptions": mock_botocore_exc, "botocore": MagicMock()}):
        result = await s3.exists("key1")
    assert result is False


# ---------------------------------------------------------------------------
# init_storage
# ---------------------------------------------------------------------------


def test_init_storage_explicit_backend():
    import vox.storage as mod

    old = mod._backend
    try:
        mock_backend = MagicMock()
        result = mod.init_storage(backend=mock_backend)
        assert result is mock_backend
        assert mod._backend is mock_backend
    finally:
        mod._backend = old


def test_init_storage_s3_from_env():
    import vox.storage as mod

    old = mod._backend
    try:
        with patch("builtins.__import__", wraps=__builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__):
            # Patch S3Storage __init__ to avoid the real aioboto3 import
            with patch.object(mod.S3Storage, "__init__", return_value=None):
                with patch.dict(os.environ, {"VOX_STORAGE_BACKEND": "s3"}):
                    result = mod.init_storage()
                    assert isinstance(result, mod.S3Storage)
    finally:
        mod._backend = old
        # Clean env
        os.environ.pop("VOX_STORAGE_BACKEND", None)

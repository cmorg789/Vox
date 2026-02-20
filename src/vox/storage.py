"""Pluggable storage backends for file uploads."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Protocol

_backend: StorageBackend | None = None


class StorageBackend(Protocol):
    """Protocol for file storage backends."""

    async def put(self, key: str, data: bytes, mime: str) -> str:
        """Store data and return the public URL path."""
        ...

    async def get(self, key: str) -> bytes:
        """Retrieve file data by key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a file by key."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if a file exists."""
        ...


class LocalStorage:
    """Store files on the local filesystem."""

    def __init__(self, base_dir: str = "uploads") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        """Resolve path and ensure it stays within base_dir (prevent path traversal)."""
        resolved = (self.base_dir / key).resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise ValueError("Invalid file key")
        return resolved

    async def put(self, key: str, data: bytes, mime: str) -> str:
        path = self._safe_path(key)
        await asyncio.to_thread(path.write_bytes, data)
        return f"/api/v1/files/{key}"

    async def get(self, key: str) -> bytes:
        path = self._safe_path(key)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._safe_path(key)
        if await asyncio.to_thread(path.exists):
            await asyncio.to_thread(path.unlink)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._safe_path(key).exists)

    @property
    def local_path(self) -> Path:
        return self.base_dir


class S3Storage:
    """Store files in an S3-compatible bucket (AWS S3, Backblaze B2, MinIO, etc.)."""

    def __init__(
        self,
        bucket: str,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        public_url: str | None = None,
    ) -> None:
        try:
            import aioboto3  # noqa: F401
        except ImportError:
            raise RuntimeError("aioboto3 is required for S3 storage: pip install aioboto3")
        self.bucket = bucket
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.public_url = public_url  # e.g. "https://cdn.example.com"
        self._session = aioboto3.Session()

    def _session_kwargs(self) -> dict:
        kwargs: dict = {}
        if self.endpoint:
            kwargs["endpoint_url"] = self.endpoint
        if self.access_key:
            kwargs["aws_access_key_id"] = self.access_key
        if self.secret_key:
            kwargs["aws_secret_access_key"] = self.secret_key
        kwargs["region_name"] = self.region
        return kwargs

    async def put(self, key: str, data: bytes, mime: str) -> str:
        async with self._session.client("s3", **self._session_kwargs()) as s3:
            await s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)
        if self.public_url:
            return f"{self.public_url}/{key}"
        return f"/api/v1/files/{key}"

    async def get(self, key: str) -> bytes:
        async with self._session.client("s3", **self._session_kwargs()) as s3:
            resp = await s3.get_object(Bucket=self.bucket, Key=key)
            return await resp["Body"].read()

    async def delete(self, key: str) -> None:
        async with self._session.client("s3", **self._session_kwargs()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        async with self._session.client("s3", **self._session_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return False


def init_storage(backend: StorageBackend | None = None) -> StorageBackend:
    """Initialize the global storage backend from env vars or an explicit backend."""
    global _backend
    if backend is not None:
        _backend = backend
        return _backend

    kind = os.environ.get("VOX_STORAGE_BACKEND", "local")
    if kind == "s3":
        _backend = S3Storage(
            bucket=os.environ.get("VOX_S3_BUCKET", "vox-uploads"),
            endpoint=os.environ.get("VOX_S3_ENDPOINT"),
            access_key=os.environ.get("VOX_S3_ACCESS_KEY"),
            secret_key=os.environ.get("VOX_S3_SECRET_KEY"),
            region=os.environ.get("VOX_S3_REGION", "us-east-1"),
            public_url=os.environ.get("VOX_S3_PUBLIC_URL"),
        )
    else:
        _backend = LocalStorage(os.environ.get("VOX_STORAGE_PATH", "uploads"))

    return _backend


def get_storage() -> StorageBackend:
    """Return the current storage backend. Must call init_storage() first."""
    if _backend is None:
        return init_storage()
    return _backend

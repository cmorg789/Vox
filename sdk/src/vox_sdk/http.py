"""HTTP client wrapping httpx with auth headers, rate limiting, and retry."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from vox_sdk.errors import VoxHTTPError, VoxNetworkError
from vox_sdk.rate_limit import RateLimiter

_MAX_RETRIES = 3
_BASE_RETRY_DELAY = 1.0
_RETRYABLE_STATUSES = {500, 502, 503, 504}


class HTTPClient:
    """Async HTTP client for the Vox REST API."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._rate_limiter = RateLimiter()
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    @property
    def token(self) -> str | None:
        return self._token

    @token.setter
    def token(self, value: str | None) -> None:
        self._token = value

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        data: Any = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an API request with rate-limit awareness and 429 retry."""
        merged_headers = self._headers()
        if headers:
            merged_headers.update(headers)

        for attempt in range(_MAX_RETRIES):
            await self._rate_limiter.wait_if_needed(path)

            try:
                response = await self._client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    data=data,
                    files=files,
                    headers=merged_headers,
                )
            except httpx.TransportError as exc:
                raise VoxNetworkError(str(exc)) from exc

            self._rate_limiter.update_from_response(path, response)

            if response.status_code == 429:
                retry_after = _BASE_RETRY_DELAY
                try:
                    body = response.json()
                    ms = body.get("error", {}).get("retry_after_ms")
                    if ms:
                        retry_after = ms / 1000.0
                except Exception:
                    ra_header = response.headers.get("retry-after")
                    if ra_header:
                        retry_after = float(ra_header)
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(retry_after)
                    continue
                raise VoxHTTPError.from_response(response)

            if response.status_code in _RETRYABLE_STATUSES:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BASE_RETRY_DELAY * (2 ** attempt))
                    continue
                raise VoxHTTPError.from_response(response)

            if response.status_code >= 400:
                raise VoxHTTPError.from_response(response)

            return response

        # Should not reach here, but just in case
        raise VoxHTTPError.from_response(response)  # type: ignore[possibly-undefined]

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", path, **kwargs)

    async def close(self) -> None:
        await self._client.aclose()

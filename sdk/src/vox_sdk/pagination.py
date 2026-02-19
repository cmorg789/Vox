"""Async iterator for cursor-based pagination."""

from __future__ import annotations

from typing import Any, AsyncIterator, TypeVar

from pydantic import BaseModel

from vox_sdk.http import HTTPClient

T = TypeVar("T", bound=BaseModel)


class PaginatedIterator(AsyncIterator[T]):
    """Yields items across cursor-paginated API responses.

    Expects response bodies with ``items`` (list) and ``cursor`` (str | None).
    """

    def __init__(
        self,
        http: HTTPClient,
        path: str,
        model: type[T],
        *,
        params: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> None:
        self._http = http
        self._path = path
        self._model = model
        self._params = dict(params) if params else {}
        self._limit = limit
        self._buffer: list[T] = []
        self._cursor: str | None = None
        self._exhausted = False
        self._started = False

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        if self._buffer:
            return self._buffer.pop(0)
        if self._exhausted:
            raise StopAsyncIteration
        await self._fetch_page()
        if not self._buffer:
            raise StopAsyncIteration
        return self._buffer.pop(0)

    async def _fetch_page(self) -> None:
        params = {**self._params, "limit": self._limit}
        if self._cursor:
            params["cursor"] = self._cursor
        r = await self._http.get(self._path, params=params)
        data = r.json()
        items = data.get("items", [])
        self._buffer = [self._model.model_validate(item) for item in items]
        self._cursor = data.get("cursor")
        if not self._cursor or not items:
            self._exhausted = True
        self._started = True

    async def flatten(self) -> list[T]:
        """Consume the full iterator into a list."""
        result: list[T] = []
        async for item in self:
            result.append(item)
        return result

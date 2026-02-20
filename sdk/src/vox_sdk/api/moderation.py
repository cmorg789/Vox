"""Moderation API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.moderation import (
    AuditLogResponse,
    ReportDetailResponse,
    ReportListResponse,
    ReportResponse,
)
from vox_sdk.pagination import PaginatedIterator

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class ModerationAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def create_report(
        self,
        reported_user_id: int,
        reason: str,
        *,
        feed_id: int | None = None,
        msg_id: int | None = None,
        dm_id: int | None = None,
        messages: list[dict] | None = None,
        description: str | None = None,
    ) -> ReportResponse:
        payload: dict[str, Any] = {
            "reported_user_id": reported_user_id,
            "reason": reason,
        }
        if feed_id is not None:
            payload["feed_id"] = feed_id
        if msg_id is not None:
            payload["msg_id"] = msg_id
        if dm_id is not None:
            payload["dm_id"] = dm_id
        if messages is not None:
            payload["messages"] = messages
        if description is not None:
            payload["description"] = description
        r = await self._http.post("/api/v1/reports", json=payload)
        return ReportResponse.model_validate(r.json())

    async def list_reports(self, **params: Any) -> ReportListResponse:
        r = await self._http.get("/api/v1/reports", params=params)
        return ReportListResponse.model_validate(r.json())

    def iter_reports(self, *, limit: int = 50) -> PaginatedIterator[ReportResponse]:
        return PaginatedIterator(self._http, "/api/v1/reports", ReportResponse, limit=limit)

    async def get_report(self, report_id: int) -> ReportDetailResponse:
        r = await self._http.get(f"/api/v1/reports/{report_id}")
        return ReportDetailResponse.model_validate(r.json())

    async def resolve_report(self, report_id: int, action: str) -> None:
        await self._http.post(
            f"/api/v1/reports/{report_id}/resolve", json={"action": action}
        )

    async def delete_report(self, report_id: int) -> None:
        await self._http.delete(f"/api/v1/reports/{report_id}")

    async def audit_log(self, **params: Any) -> AuditLogResponse:
        r = await self._http.get("/api/v1/audit-log", params=params)
        return AuditLogResponse.model_validate(r.json())

    async def admin_2fa_reset(self, target_user_id: int, reason: str) -> None:
        await self._http.post(
            "/api/v1/admin/2fa-reset",
            json={"target_user_id": target_user_id, "reason": reason},
        )

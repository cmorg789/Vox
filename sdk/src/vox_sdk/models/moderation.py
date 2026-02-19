from vox_sdk.models.base import VoxModel


class ReportResponse(VoxModel):
    report_id: int
    reporter_id: int | None = None
    reported_user_id: int | None = None
    reason: str | None = None
    status: str | None = None
    created_at: int | None = None


class ReportListResponse(VoxModel):
    items: list[ReportResponse] = []
    cursor: str | None = None


class ReportDetailResponse(VoxModel):
    report_id: int
    reporter_id: int
    reported_user_id: int
    feed_id: int | None = None
    msg_id: int | None = None
    dm_id: int | None = None
    reason: str
    description: str | None = None
    evidence: list | None = None
    status: str
    action: str | None = None
    created_at: int = 0


class AuditLogEntry(VoxModel):
    entry_id: int
    event_type: str
    actor_id: int
    target_id: int | None = None
    metadata: dict | None = None
    timestamp: int = 0


class AuditLogResponse(VoxModel):
    entries: list[AuditLogEntry] = []
    cursor: str | None = None

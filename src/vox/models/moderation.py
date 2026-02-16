from pydantic import BaseModel, Field

from vox.limits import ADMIN_REASON_MAX, REPORT_DESCRIPTION_MAX, REPORT_REASON_MAX
from vox.models.base import VoxModel


# --- Reports ---


class ReportMessageData(BaseModel):
    msg_id: int
    body: str
    timestamp: int


class CreateReportRequest(BaseModel):
    reported_user_id: int
    feed_id: int | None = None
    msg_id: int | None = None
    dm_id: int | None = None
    messages: list[ReportMessageData] | None = None
    reason: str = Field(max_length=REPORT_REASON_MAX)  # harassment, spam, illegal_content, threats, other
    description: str | None = Field(default=None, max_length=REPORT_DESCRIPTION_MAX)


class ResolveReportRequest(BaseModel):
    action: str  # dismiss, warn, kick, ban


class ReportResponse(VoxModel):
    report_id: int


# --- Audit Log ---


class AuditLogEntry(VoxModel):
    entry_id: int
    event_type: str
    actor_id: int
    target_id: int | None = None
    metadata: dict | None = None
    timestamp: int


class AuditLogResponse(VoxModel):
    entries: list[AuditLogEntry]
    cursor: str | None = None


# --- Admin ---


class Admin2FAResetRequest(BaseModel):
    target_user_id: int
    reason: str = Field(max_length=ADMIN_REASON_MAX)

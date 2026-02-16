from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.limits import str_limit
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
    reason: Annotated[str, AfterValidator(str_limit(max_attr="report_reason_max"))]  # harassment, spam, illegal_content, threats, other
    description: Annotated[str, AfterValidator(str_limit(max_attr="report_description_max"))] | None = None


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
    reason: Annotated[str, AfterValidator(str_limit(max_attr="admin_reason_max"))]

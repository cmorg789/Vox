import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select

from vox.api.messages import _snowflake
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import AuditLog, RecoveryCode, Report, TOTPSecret, User, WebAuthnCredential
from vox.limits import limits
from vox.permissions import MANAGE_2FA, VIEW_AUDIT_LOG, VIEW_REPORTS
from vox.models.moderation import (
    AuditLogEntry,
    AuditLogResponse,
    Admin2FAResetRequest,
    CreateReportRequest,
    ReportResponse,
    ResolveReportRequest,
)

router = APIRouter(tags=["moderation"])


# --- Reports ---

@router.post("/api/v1/reports", status_code=201)
async def create_report(
    body: CreateReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportResponse:
    import json
    evidence = json.dumps([m.model_dump() for m in body.messages]) if body.messages else None
    report = Report(
        reporter_id=user.id,
        reported_user_id=body.reported_user_id,
        feed_id=body.feed_id,
        msg_id=body.msg_id,
        dm_id=body.dm_id,
        reason=body.reason,
        description=body.description,
        evidence=evidence,
        created_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.flush()
    await db.commit()
    return ReportResponse(report_id=report.id)


@router.get("/api/v1/reports")
async def list_reports(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(VIEW_REPORTS),
):
    limit = min(limit, limits.page_limit_reports)
    query = select(Report).order_by(Report.id).limit(limit)
    if status is not None:
        query = query.where(Report.status == status)
    if after is not None:
        query = query.where(Report.id > after)
    result = await db.execute(query)
    reports = result.scalars().all()
    items = [{"report_id": r.id, "reporter_id": r.reporter_id, "reported_user_id": r.reported_user_id, "reason": r.reason, "status": r.status} for r in reports]
    cursor = str(reports[-1].id) if reports else None
    return {"items": items, "cursor": cursor}


@router.post("/api/v1/reports/{report_id}/resolve", status_code=204)
async def resolve_report(
    report_id: int,
    body: ResolveReportRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(VIEW_REPORTS),
):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "REPORT_NOT_FOUND", "message": "Report does not exist."}})
    report.status = "resolved"
    report.action = body.action
    await db.commit()


# --- Audit Log ---

@router.get("/api/v1/audit-log")
async def query_audit_log(
    event_type: str | None = None,
    actor_id: int | None = None,
    target_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(VIEW_AUDIT_LOG),
) -> AuditLogResponse:
    limit = min(limit, limits.page_limit_audit_log)
    query = select(AuditLog).order_by(AuditLog.id).limit(limit)
    if event_type is not None:
        escaped = event_type.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("*", "%")
        query = query.where(AuditLog.event_type.like(escaped, escape="\\"))
    if actor_id is not None:
        query = query.where(AuditLog.actor_id == actor_id)
    if target_id is not None:
        query = query.where(AuditLog.target_id == target_id)
    if after is not None:
        query = query.where(AuditLog.id > after)
    result = await db.execute(query)
    import json
    rows = result.scalars().all()
    entries = []
    for e in rows:
        meta = json.loads(e.extra) if e.extra else None
        entries.append(AuditLogEntry(entry_id=e.id, event_type=e.event_type, actor_id=e.actor_id, target_id=e.target_id, metadata=meta, timestamp=e.timestamp))
    cursor = str(rows[-1].id) if rows else None
    return AuditLogResponse(entries=entries, cursor=cursor)


# --- Admin ---

@router.post("/api/v1/admin/2fa-reset", status_code=204)
async def admin_2fa_reset(
    body: Admin2FAResetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(MANAGE_2FA),
):
    # Delete all 2FA for target user
    await db.execute(delete(TOTPSecret).where(TOTPSecret.user_id == body.target_user_id))
    await db.execute(delete(WebAuthnCredential).where(WebAuthnCredential.user_id == body.target_user_id))
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == body.target_user_id))

    # Audit log
    from vox.audit import write_audit
    await write_audit(db, "2fa.admin_reset", actor_id=user.id, target_id=body.target_user_id, extra={"reason": body.reason})
    await db.commit()

"""Shared audit-log helper."""

import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.messages import _snowflake
from vox.db.models import AuditLog


async def write_audit(
    db: AsyncSession,
    event_type: str,
    actor_id: int,
    target_id: int | None = None,
    extra: dict | None = None,
) -> None:
    db.add(AuditLog(
        id=await _snowflake(),
        event_type=event_type,
        actor_id=actor_id,
        target_id=target_id,
        extra=json.dumps(extra) if extra else None,
        timestamp=int(time.time() * 1000),
    ))

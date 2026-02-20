"""FastAPI dependency for verifying inbound federation requests."""

from __future__ import annotations

import time

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_db
from vox.federation.service import check_federation_allowed, verify_signature_for_origin

# Maximum age (seconds) for a federation request timestamp before rejection.
_FED_MAX_SKEW = 300


async def verify_federation_request(
    request: Request,
    x_vox_origin: str = Header(...),
    x_vox_signature: str = Header(...),
    x_vox_timestamp: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Verify an inbound S2S request. Returns the verified origin domain."""
    body = await request.body()

    # Reject requests without a timestamp or with a stale/future timestamp.
    try:
        ts = int(x_vox_timestamp)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "FED_MISSING_TIMESTAMP", "message": "Missing or invalid X-Vox-Timestamp header."}},
        )
    now = int(time.time())
    if abs(now - ts) > _FED_MAX_SKEW:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FED_TIMESTAMP_EXPIRED", "message": "Federation request timestamp is too old or too far in the future."}},
        )

    # Signature covers body + timestamp to prevent replay with altered timestamp.
    signed_payload = body + x_vox_timestamp.encode()
    if not await verify_signature_for_origin(signed_payload, x_vox_signature, x_vox_origin):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FED_AUTH_FAILED", "message": "Invalid federation signature."}},
        )

    if not await check_federation_allowed(db, x_vox_origin, direction="inbound"):
        # Check if domain is explicitly blocked
        from sqlalchemy import select
        from vox.db.models import FederationEntry

        result = await db.execute(
            select(FederationEntry).where(FederationEntry.entry == x_vox_origin)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "FED_BLOCKED", "message": "Origin domain is blocked."}},
            )
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FED_POLICY_DENIED", "message": "Federation policy denies this request."}},
        )

    return x_vox_origin

"""FastAPI dependency for verifying inbound federation requests."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_db
from vox.federation.service import check_federation_allowed, verify_signature_for_origin


async def verify_federation_request(
    request: Request,
    x_vox_origin: str = Header(...),
    x_vox_signature: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Verify an inbound S2S request. Returns the verified origin domain."""
    body = await request.body()

    if not await verify_signature_for_origin(body, x_vox_signature, x_vox_origin):
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

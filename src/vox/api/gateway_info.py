from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_db
from vox.api.server import _get_config
from vox.models.server import GatewayInfoResponse

router = APIRouter(tags=["gateway"])


@router.get("/api/v1/gateway")
async def get_gateway_info(
    db: AsyncSession = Depends(get_db),
) -> GatewayInfoResponse:
    # No auth required
    url = await _get_config(db, "gateway_url") or "wss://localhost/gateway"
    media_url = await _get_config(db, "media_url") or "quic://localhost:4443"
    return GatewayInfoResponse(url=url, media_url=media_url, protocol_version=1, min_version=1, max_version=1)

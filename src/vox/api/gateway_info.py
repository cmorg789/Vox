from fastapi import APIRouter

from vox.config import config
from vox.models.server import GatewayInfoResponse

router = APIRouter(tags=["gateway"])


@router.get("/api/v1/gateway")
async def get_gateway_info() -> GatewayInfoResponse:
    # No auth required
    return GatewayInfoResponse(
        url=config.server.gateway_url,
        media_url=config.media.url,
        protocol_version=1,
        min_version=1,
        max_version=1,
    )

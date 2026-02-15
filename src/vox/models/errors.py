from vox.models.base import VoxModel


class ErrorResponse(VoxModel):
    code: str
    message: str
    retry_after_ms: int | None = None
    missing_permission: str | None = None

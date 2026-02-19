from vox_sdk.models.base import VoxModel


class FileResponse(VoxModel):
    file_id: str
    name: str
    size: int
    mime: str
    url: str
    uploader_id: int | None = None
    created_at: int | None = None
    width: int | None = None
    height: int | None = None

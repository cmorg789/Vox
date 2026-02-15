from vox.models.base import VoxModel


class FileResponse(VoxModel):
    file_id: str
    name: str
    size: int
    mime: str
    url: str

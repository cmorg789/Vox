from vox_sdk.models.base import VoxModel


class RoleResponse(VoxModel):
    role_id: int
    name: str
    color: int | None = None
    permissions: int = 0
    position: int = 0


class RoleListResponse(VoxModel):
    items: list[RoleResponse] = []
    cursor: str | None = None

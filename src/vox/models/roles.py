from pydantic import BaseModel

from vox.models.base import VoxModel


class RoleResponse(VoxModel):
    role_id: int
    name: str
    color: int | None
    permissions: int
    position: int


class CreateRoleRequest(BaseModel):
    name: str
    color: int | None = None
    permissions: int
    position: int


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    color: int | None = None
    permissions: int | None = None
    position: int | None = None


class PermissionOverrideRequest(BaseModel):
    allow: int
    deny: int

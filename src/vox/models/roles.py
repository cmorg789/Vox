from pydantic import BaseModel, Field

from vox.limits import ROLE_NAME_MAX, ROLE_NAME_MIN
from vox.models.base import VoxModel


class RoleResponse(VoxModel):
    role_id: int
    name: str
    color: int | None
    permissions: int
    position: int


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=ROLE_NAME_MIN, max_length=ROLE_NAME_MAX)
    color: int | None = None
    permissions: int
    position: int


class UpdateRoleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=ROLE_NAME_MAX)
    color: int | None = None
    permissions: int | None = None
    position: int | None = None


class PermissionOverrideRequest(BaseModel):
    allow: int
    deny: int

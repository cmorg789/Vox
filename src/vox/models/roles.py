from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.config import str_limit
from vox.models.base import VoxModel


class RoleResponse(VoxModel):
    role_id: int
    name: str
    color: int | None
    permissions: int
    position: int


class CreateRoleRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(min_attr="role_name_min", max_attr="role_name_max"))]
    color: int | None = None
    permissions: int
    position: int


class UpdateRoleRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="role_name_max"))] | None = None
    color: int | None = None
    permissions: int | None = None
    position: int | None = None


class PermissionOverrideRequest(BaseModel):
    allow: int
    deny: int

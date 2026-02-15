from pydantic import BaseModel


class VoxModel(BaseModel):
    model_config = {"from_attributes": True}

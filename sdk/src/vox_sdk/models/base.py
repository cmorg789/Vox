from pydantic import BaseModel


class VoxModel(BaseModel):
    """Base model for all SDK response types."""

    model_config = {"extra": "ignore"}

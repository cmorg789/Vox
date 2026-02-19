from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.config import str_limit
from vox.models.base import VoxModel


class EmojiResponse(VoxModel):
    emoji_id: int
    name: str
    creator_id: int
    image: str | None = None


class UpdateEmojiRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="emoji_name_max"))]


class UpdateStickerRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="emoji_name_max"))]


class StickerResponse(VoxModel):
    sticker_id: int
    name: str
    creator_id: int
    image: str | None = None

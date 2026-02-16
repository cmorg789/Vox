from vox.models.base import VoxModel


class EmojiResponse(VoxModel):
    emoji_id: int
    name: str
    creator_id: int
    image: str | None = None


class StickerResponse(VoxModel):
    sticker_id: int
    name: str
    creator_id: int
    image: str | None = None

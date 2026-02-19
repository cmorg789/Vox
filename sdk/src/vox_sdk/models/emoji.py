from vox_sdk.models.base import VoxModel


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


class EmojiListResponse(VoxModel):
    items: list[EmojiResponse] = []
    cursor: str | None = None


class StickerListResponse(VoxModel):
    items: list[StickerResponse] = []
    cursor: str | None = None

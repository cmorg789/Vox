from vox_sdk.models.base import VoxModel
from vox_sdk.models.bots import Embed
from vox_sdk.models.files import FileResponse


class SendMessageResponse(VoxModel):
    msg_id: int
    timestamp: int
    interaction_id: str | None = None
    mentions: list[int] | None = None


class EditMessageResponse(VoxModel):
    msg_id: int
    edit_timestamp: int


class MessageResponse(VoxModel):
    msg_id: int
    feed_id: int | None = None
    dm_id: int | None = None
    thread_id: int | None = None
    author_id: int | None = None
    body: str | None = None
    opaque_blob: str | None = None
    timestamp: int = 0
    reply_to: int | None = None
    attachments: list[FileResponse] = []
    embed: Embed | None = None
    edit_timestamp: int | None = None
    federated: bool = False
    author_address: str | None = None
    pinned_at: int | None = None
    webhook_id: int | None = None


class MessageListResponse(VoxModel):
    messages: list[MessageResponse] = []


class ReactionGroup(VoxModel):
    emoji: str
    user_ids: list[int] = []


class ReactionListResponse(VoxModel):
    reactions: list[ReactionGroup] = []


class SearchResponse(VoxModel):
    results: list[MessageResponse] = []

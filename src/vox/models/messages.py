from pydantic import BaseModel

from vox.models.base import VoxModel


class MentionData(BaseModel):
    user_id: int


class SendMessageRequest(BaseModel):
    body: str
    reply_to: int | None = None
    mentions: list[MentionData] | None = None
    embeds: list | None = None
    attachments: list[str] | None = None  # file_ids
    components: list | None = None  # bot components


class EditMessageRequest(BaseModel):
    body: str


class SendMessageResponse(VoxModel):
    msg_id: int
    timestamp: int


class EditMessageResponse(VoxModel):
    msg_id: int
    edit_timestamp: int


class MessageResponse(VoxModel):
    msg_id: int
    feed_id: int | None = None
    dm_id: int | None = None
    author_id: int
    body: str | None = None
    opaque_blob: str | None = None
    timestamp: int
    reply_to: int | None = None
    mentions: list[MentionData] = []
    embeds: list = []
    attachments: list = []
    components: list = []
    edit_timestamp: int | None = None
    federated: bool = False
    author_address: str | None = None


class MessageListResponse(VoxModel):
    messages: list[MessageResponse]


class BulkDeleteRequest(BaseModel):
    msg_ids: list[int]


# --- Search ---


class SearchResponse(VoxModel):
    results: list[MessageResponse]


# --- Embeds ---


class ResolveEmbedRequest(BaseModel):
    url: str


class EmbedResponse(VoxModel):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    video: str | None = None

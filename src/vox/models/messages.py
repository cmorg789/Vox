from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.limits import list_limit, str_limit
from vox.models.base import VoxModel


class SendMessageRequest(BaseModel):
    body: Annotated[str, AfterValidator(str_limit(max_attr="message_body_max"))]
    reply_to: int | None = None
    attachments: list[str] | None = None  # file_ids
    mentions: list[int] | None = None
    embed: str | None = None


class EditMessageRequest(BaseModel):
    body: Annotated[str, AfterValidator(str_limit(max_attr="message_body_max"))]


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
    timestamp: int
    reply_to: int | None = None
    attachments: list = []
    embed: str | None = None
    edit_timestamp: int | None = None
    federated: bool = False
    author_address: str | None = None
    pinned_at: int | None = None
    webhook_id: int | None = None


class MessageListResponse(VoxModel):
    messages: list[MessageResponse]


class BulkDeleteRequest(BaseModel):
    msg_ids: Annotated[list[int], AfterValidator(list_limit(max_attr="bulk_delete_max"))]


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

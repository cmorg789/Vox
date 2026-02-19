from vox_sdk.models.base import VoxModel


class EmbedField(VoxModel):
    name: str
    value: str
    inline: bool = False


class Embed(VoxModel):
    title: str | None = None
    description: str | None = None
    url: str | None = None
    site_name: str | None = None
    image: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    video: str | None = None
    video_width: int | None = None
    video_height: int | None = None
    audio: str | None = None
    type: str | None = None
    locale: str | None = None
    color: int | None = None
    fields: list[EmbedField] | None = None
    thumbnail: str | None = None


class WebhookResponse(VoxModel):
    webhook_id: int
    feed_id: int
    name: str
    token: str
    avatar: str | None = None


class WebhookListItem(VoxModel):
    webhook_id: int
    feed_id: int
    name: str
    avatar: str | None = None


class WebhookListWrapper(VoxModel):
    webhooks: list[WebhookListItem] = []


class CommandParam(VoxModel):
    name: str
    description: str | None = None
    required: bool = False


class CommandResponse(VoxModel):
    name: str
    description: str | None = None
    params: list[CommandParam] = []


class CommandListResponse(VoxModel):
    commands: list[CommandResponse] = []


class OkResponse(VoxModel):
    ok: bool = True

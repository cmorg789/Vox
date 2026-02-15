from pydantic import BaseModel

from vox.models.base import VoxModel


# --- Webhooks ---


class CreateWebhookRequest(BaseModel):
    name: str
    avatar: str | None = None


class WebhookResponse(VoxModel):
    webhook_id: int
    feed_id: int
    name: str
    token: str


class ExecuteWebhookRequest(BaseModel):
    body: str
    embeds: list | None = None


# --- Bot Commands ---


class CommandParam(BaseModel):
    name: str
    description: str | None = None
    required: bool = False


class CommandData(BaseModel):
    name: str
    description: str | None = None
    params: list[CommandParam] | None = None


class RegisterCommandsRequest(BaseModel):
    commands: list[CommandData]


class DeregisterCommandsRequest(BaseModel):
    command_names: list[str]


class CommandResponse(VoxModel):
    name: str
    description: str | None = None
    params: list[CommandParam] = []


# --- Interactions ---


class InteractionResponse(BaseModel):
    body: str | None = None
    embeds: list | None = None
    components: list | None = None
    ephemeral: bool = False

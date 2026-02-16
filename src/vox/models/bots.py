from pydantic import BaseModel, Field

from vox.limits import COMMAND_DESCRIPTION_MAX, COMMAND_NAME_MAX, MESSAGE_BODY_MAX, WEBHOOK_NAME_MAX
from vox.models.base import VoxModel


# --- Webhooks ---


class CreateWebhookRequest(BaseModel):
    name: str = Field(max_length=WEBHOOK_NAME_MAX)
    avatar: str | None = None


class WebhookResponse(VoxModel):
    webhook_id: int
    feed_id: int
    name: str
    token: str


class ExecuteWebhookRequest(BaseModel):
    body: str = Field(max_length=MESSAGE_BODY_MAX)
    embeds: list | None = None


# --- Bot Commands ---


class CommandParam(BaseModel):
    name: str = Field(max_length=COMMAND_NAME_MAX)
    description: str | None = Field(default=None, max_length=COMMAND_DESCRIPTION_MAX)
    required: bool = False


class CommandData(BaseModel):
    name: str = Field(max_length=COMMAND_NAME_MAX)
    description: str | None = Field(default=None, max_length=COMMAND_DESCRIPTION_MAX)
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


class ComponentInteractionRequest(BaseModel):
    msg_id: int
    component_id: str

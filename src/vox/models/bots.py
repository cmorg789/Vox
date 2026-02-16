from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.limits import str_limit
from vox.models.base import VoxModel


# --- Webhooks ---


class CreateWebhookRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="webhook_name_max"))]
    avatar: str | None = None


class WebhookResponse(VoxModel):
    webhook_id: int
    feed_id: int
    name: str
    token: str


class ExecuteWebhookRequest(BaseModel):
    body: Annotated[str, AfterValidator(str_limit(max_attr="message_body_max"))]
    embeds: list | None = None


# --- Bot Commands ---


class CommandParam(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="command_name_max"))]
    description: Annotated[str, AfterValidator(str_limit(max_attr="command_description_max"))] | None = None
    required: bool = False


class CommandData(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="command_name_max"))]
    description: Annotated[str, AfterValidator(str_limit(max_attr="command_description_max"))] | None = None
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

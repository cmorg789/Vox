from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel

from vox.limits import str_limit
from vox.models.base import VoxModel


# --- Embed / Component Models ---


class EmbedField(BaseModel):
    name: str
    value: str
    inline: bool = False


class Embed(BaseModel):
    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    fields: list[EmbedField] | None = None
    image: str | None = None
    thumbnail: str | None = None


class ActionButton(BaseModel):
    type: Literal["button"]
    label: str
    custom_id: str
    style: str = "primary"


class SelectOption(BaseModel):
    label: str
    value: str
    description: str | None = None


class SelectMenu(BaseModel):
    type: Literal["select"]
    custom_id: str
    options: list[SelectOption]
    placeholder: str | None = None


Component = ActionButton | SelectMenu


# --- Webhooks ---


class CreateWebhookRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="webhook_name_max"))]
    avatar: str | None = None


class WebhookResponse(VoxModel):
    webhook_id: int
    feed_id: int
    name: str
    token: str
    avatar: str | None = None


class ExecuteWebhookRequest(BaseModel):
    body: Annotated[str, AfterValidator(str_limit(max_attr="message_body_max"))]
    embeds: list[Embed] | None = None


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
    embeds: list[Embed] | None = None
    components: list[Component] | None = None
    ephemeral: bool = False


class ComponentInteractionRequest(BaseModel):
    msg_id: int
    component_id: str

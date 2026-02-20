"""Gateway event dataclasses — lightweight containers for received events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayEvent:
    """Base for all gateway events."""
    type: str
    seq: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


# --- Control ---

@dataclass
class Hello(GatewayEvent):
    heartbeat_interval: int = 45000

@dataclass
class Ready(GatewayEvent):
    session_id: str = ""
    user_id: int = 0
    display_name: str = ""
    server_name: str = ""
    server_icon: str | None = None
    server_time: int | None = None
    protocol_version: int = 1
    capabilities: list[str] = field(default_factory=list)

@dataclass
class Resumed(GatewayEvent):
    pass  # seq is on base


# --- Messages ---

@dataclass
class MessageCreate(GatewayEvent):
    msg_id: int = 0
    feed_id: int | None = None
    dm_id: int | None = None
    author_id: int | None = None
    body: str | None = None
    timestamp: int = 0
    reply_to: int | None = None
    mentions: list[int] = field(default_factory=list)
    webhook_id: int | None = None
    embed: dict | None = None
    attachments: list[dict] = field(default_factory=list)

@dataclass
class MessageUpdate(GatewayEvent):
    msg_id: int = 0
    feed_id: int | None = None
    dm_id: int | None = None
    body: str | None = None
    edit_timestamp: int | None = None

@dataclass
class MessageDelete(GatewayEvent):
    msg_id: int = 0
    feed_id: int | None = None
    dm_id: int | None = None

@dataclass
class MessageBulkDelete(GatewayEvent):
    feed_id: int = 0
    msg_ids: list[int] = field(default_factory=list)

@dataclass
class MessageReactionAdd(GatewayEvent):
    msg_id: int = 0
    user_id: int = 0
    emoji: str = ""

@dataclass
class MessageReactionRemove(GatewayEvent):
    msg_id: int = 0
    user_id: int = 0
    emoji: str = ""

@dataclass
class MessagePinUpdate(GatewayEvent):
    msg_id: int = 0
    feed_id: int = 0
    pinned: bool = False


# --- Members ---

@dataclass
class MemberJoin(GatewayEvent):
    user_id: int = 0
    display_name: str | None = None

@dataclass
class MemberLeave(GatewayEvent):
    user_id: int = 0

@dataclass
class MemberUpdate(GatewayEvent):
    user_id: int = 0
    nickname: str | None = None

@dataclass
class UserUpdate(GatewayEvent):
    user_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class MemberBan(GatewayEvent):
    user_id: int = 0

@dataclass
class MemberUnban(GatewayEvent):
    user_id: int = 0


# --- Channels ---

@dataclass
class FeedCreate(GatewayEvent):
    feed_id: int = 0
    name: str = ""
    type: str | None = None
    topic: str | None = None
    category_id: int | None = None

@dataclass
class FeedUpdate(GatewayEvent):
    feed_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class FeedDelete(GatewayEvent):
    feed_id: int = 0

@dataclass
class RoomCreate(GatewayEvent):
    room_id: int = 0
    name: str = ""
    type: str | None = None
    category_id: int | None = None

@dataclass
class RoomUpdate(GatewayEvent):
    room_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class RoomDelete(GatewayEvent):
    room_id: int = 0

@dataclass
class CategoryCreate(GatewayEvent):
    category_id: int = 0
    name: str = ""
    position: int | None = None

@dataclass
class CategoryUpdate(GatewayEvent):
    category_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class CategoryDelete(GatewayEvent):
    category_id: int = 0

@dataclass
class ThreadCreate(GatewayEvent):
    thread_id: int = 0
    parent_feed_id: int = 0
    name: str = ""
    parent_msg_id: int | None = None

@dataclass
class ThreadUpdate(GatewayEvent):
    thread_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class ThreadDelete(GatewayEvent):
    thread_id: int = 0

@dataclass
class ThreadSubscribe(GatewayEvent):
    thread_id: int = 0
    user_id: int = 0

@dataclass
class ThreadUnsubscribe(GatewayEvent):
    thread_id: int = 0
    user_id: int = 0


# --- Roles ---

@dataclass
class RoleCreate(GatewayEvent):
    role_id: int = 0
    name: str = ""
    color: int | None = None
    permissions: int = 0
    position: int = 0

@dataclass
class RoleUpdate(GatewayEvent):
    role_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class RoleDelete(GatewayEvent):
    role_id: int = 0

@dataclass
class PermissionOverrideUpdate(GatewayEvent):
    space_type: str = ""
    space_id: int = 0
    target_type: str = ""
    target_id: int = 0
    allow: int = 0
    deny: int = 0

@dataclass
class PermissionOverrideDelete(GatewayEvent):
    space_type: str = ""
    space_id: int = 0
    target_type: str = ""
    target_id: int = 0

@dataclass
class RoleAssign(GatewayEvent):
    role_id: int = 0
    user_id: int = 0

@dataclass
class RoleRevoke(GatewayEvent):
    role_id: int = 0
    user_id: int = 0


# --- Emoji/Sticker ---

@dataclass
class EmojiCreate(GatewayEvent):
    emoji_id: int = 0
    name: str = ""
    creator_id: int = 0

@dataclass
class EmojiUpdate(GatewayEvent):
    emoji_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class EmojiDelete(GatewayEvent):
    emoji_id: int = 0

@dataclass
class StickerCreate(GatewayEvent):
    sticker_id: int = 0
    name: str = ""
    creator_id: int = 0

@dataclass
class StickerUpdate(GatewayEvent):
    sticker_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class StickerDelete(GatewayEvent):
    sticker_id: int = 0


# --- Server ---

@dataclass
class ServerUpdate(GatewayEvent):
    extra: dict[str, Any] = field(default_factory=dict)


# --- Invites ---

@dataclass
class InviteCreate(GatewayEvent):
    code: str = ""
    creator_id: int = 0
    feed_id: int | None = None

@dataclass
class InviteDelete(GatewayEvent):
    code: str = ""


# --- DMs ---

@dataclass
class DMCreate(GatewayEvent):
    dm_id: int = 0
    participant_ids: list[int] = field(default_factory=list)
    is_group: bool = False
    name: str | None = None

@dataclass
class DMUpdate(GatewayEvent):
    dm_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class DMRecipientAdd(GatewayEvent):
    dm_id: int = 0
    user_id: int = 0

@dataclass
class DMRecipientRemove(GatewayEvent):
    dm_id: int = 0
    user_id: int = 0

@dataclass
class DMReadNotify(GatewayEvent):
    dm_id: int = 0
    user_id: int = 0
    up_to_msg_id: int = 0


# --- Presence ---

@dataclass
class TypingStart(GatewayEvent):
    user_id: int = 0
    feed_id: int | None = None
    dm_id: int | None = None

@dataclass
class PresenceUpdate(GatewayEvent):
    user_id: int = 0
    status: str = ""
    custom_status: str | None = None
    activity: dict | None = None


# --- Friends/Blocks ---

@dataclass
class FriendRequest(GatewayEvent):
    user_id: int = 0
    target_id: int = 0

@dataclass
class FriendAdd(GatewayEvent):
    user_id: int = 0
    target_id: int = 0

@dataclass
class FriendReject(GatewayEvent):
    user_id: int = 0
    target_id: int = 0

@dataclass
class FriendRemove(GatewayEvent):
    user_id: int = 0
    target_id: int = 0

@dataclass
class BlockAdd(GatewayEvent):
    user_id: int = 0
    target_id: int = 0

@dataclass
class BlockRemove(GatewayEvent):
    user_id: int = 0
    target_id: int = 0


# --- Voice/Stage ---

@dataclass
class VoiceStateUpdate(GatewayEvent):
    room_id: int = 0
    members: list[dict] = field(default_factory=list)

@dataclass
class VoiceCodecNeg(GatewayEvent):
    media_type: str = ""
    codec: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class StageRequest(GatewayEvent):
    room_id: int = 0
    user_id: int = 0

@dataclass
class StageInvite(GatewayEvent):
    room_id: int = 0
    user_id: int = 0

@dataclass
class StageInviteDecline(GatewayEvent):
    room_id: int = 0
    user_id: int = 0

@dataclass
class StageRevoke(GatewayEvent):
    room_id: int = 0
    user_id: int = 0

@dataclass
class StageTopicUpdate(GatewayEvent):
    room_id: int = 0
    topic: str = ""

@dataclass
class StageResponse(GatewayEvent):
    user_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class MediaTokenRefresh(GatewayEvent):
    room_id: int = 0
    media_token: str = ""


# --- E2EE ---

@dataclass
class MLSWelcome(GatewayEvent):
    data: str = ""

@dataclass
class MLSCommit(GatewayEvent):
    data: str = ""

@dataclass
class MLSProposal(GatewayEvent):
    data: str = ""

@dataclass
class DeviceListUpdate(GatewayEvent):
    devices: list[dict] = field(default_factory=list)

@dataclass
class DevicePairPrompt(GatewayEvent):
    device_name: str = ""
    ip: str = ""
    location: str = ""
    pair_id: str = ""

@dataclass
class CPaceISI(GatewayEvent):
    pair_id: str = ""
    data: str = ""

@dataclass
class CPaceRSI(GatewayEvent):
    pair_id: str = ""
    data: str = ""

@dataclass
class CPaceConfirm(GatewayEvent):
    pair_id: str = ""
    data: str = ""

@dataclass
class CPaceNewDeviceKey(GatewayEvent):
    pair_id: str = ""
    data: str = ""
    nonce: str = ""

@dataclass
class KeyResetNotify(GatewayEvent):
    user_id: int = 0


# --- Webhooks ---

@dataclass
class WebhookCreate(GatewayEvent):
    webhook_id: int = 0
    feed_id: int = 0
    name: str = ""

@dataclass
class WebhookUpdate(GatewayEvent):
    webhook_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class WebhookDelete(GatewayEvent):
    webhook_id: int = 0


# --- Bots ---

@dataclass
class BotCommandsUpdate(GatewayEvent):
    bot_id: int = 0
    commands: list[dict] = field(default_factory=list)

@dataclass
class BotCommandsDelete(GatewayEvent):
    bot_id: int = 0
    command_names: list[str] = field(default_factory=list)

@dataclass
class InteractionCreate(GatewayEvent):
    interaction: dict = field(default_factory=dict)


# --- Feed Subscription ---

@dataclass
class FeedSubscribe(GatewayEvent):
    feed_id: int = 0
    user_id: int = 0

@dataclass
class FeedUnsubscribe(GatewayEvent):
    feed_id: int = 0
    user_id: int = 0


# --- Notifications ---

@dataclass
class NotificationCreate(GatewayEvent):
    user_id: int = 0
    notification_type: str = ""
    feed_id: int | None = None
    thread_id: int | None = None
    msg_id: int | None = None
    actor_id: int | None = None
    body_preview: str | None = None


# ---------------------------------------------------------------------------
# Event type string → dataclass mapping
# ---------------------------------------------------------------------------

_EVENT_MAP: dict[str, type[GatewayEvent]] = {
    "hello": Hello,
    "ready": Ready,
    "resumed": Resumed,
    "message_create": MessageCreate,
    "message_update": MessageUpdate,
    "message_delete": MessageDelete,
    "message_bulk_delete": MessageBulkDelete,
    "message_reaction_add": MessageReactionAdd,
    "message_reaction_remove": MessageReactionRemove,
    "message_pin_update": MessagePinUpdate,
    "member_join": MemberJoin,
    "member_leave": MemberLeave,
    "member_update": MemberUpdate,
    "user_update": UserUpdate,
    "member_ban": MemberBan,
    "member_unban": MemberUnban,
    "feed_create": FeedCreate,
    "feed_update": FeedUpdate,
    "feed_delete": FeedDelete,
    "room_create": RoomCreate,
    "room_update": RoomUpdate,
    "room_delete": RoomDelete,
    "category_create": CategoryCreate,
    "category_update": CategoryUpdate,
    "category_delete": CategoryDelete,
    "thread_create": ThreadCreate,
    "thread_update": ThreadUpdate,
    "thread_delete": ThreadDelete,
    "thread_subscribe": ThreadSubscribe,
    "thread_unsubscribe": ThreadUnsubscribe,
    "role_create": RoleCreate,
    "role_update": RoleUpdate,
    "role_delete": RoleDelete,
    "permission_override_update": PermissionOverrideUpdate,
    "permission_override_delete": PermissionOverrideDelete,
    "role_assign": RoleAssign,
    "role_revoke": RoleRevoke,
    "emoji_create": EmojiCreate,
    "emoji_update": EmojiUpdate,
    "emoji_delete": EmojiDelete,
    "sticker_create": StickerCreate,
    "sticker_update": StickerUpdate,
    "sticker_delete": StickerDelete,
    "server_update": ServerUpdate,
    "invite_create": InviteCreate,
    "invite_delete": InviteDelete,
    "dm_create": DMCreate,
    "dm_update": DMUpdate,
    "dm_recipient_add": DMRecipientAdd,
    "dm_recipient_remove": DMRecipientRemove,
    "dm_read_notify": DMReadNotify,
    "typing_start": TypingStart,
    "presence_update": PresenceUpdate,
    "friend_request": FriendRequest,
    "friend_add": FriendAdd,
    "friend_reject": FriendReject,
    "friend_remove": FriendRemove,
    "block_add": BlockAdd,
    "block_remove": BlockRemove,
    "voice_state_update": VoiceStateUpdate,
    "voice_codec_neg": VoiceCodecNeg,
    "stage_request": StageRequest,
    "stage_invite": StageInvite,
    "stage_invite_decline": StageInviteDecline,
    "stage_revoke": StageRevoke,
    "stage_topic_update": StageTopicUpdate,
    "stage_response": StageResponse,
    "media_token_refresh": MediaTokenRefresh,
    "mls_welcome": MLSWelcome,
    "mls_commit": MLSCommit,
    "mls_proposal": MLSProposal,
    "device_list_update": DeviceListUpdate,
    "device_pair_prompt": DevicePairPrompt,
    "cpace_isi": CPaceISI,
    "cpace_rsi": CPaceRSI,
    "cpace_confirm": CPaceConfirm,
    "cpace_new_device_key": CPaceNewDeviceKey,
    "key_reset_notify": KeyResetNotify,
    "webhook_create": WebhookCreate,
    "webhook_update": WebhookUpdate,
    "webhook_delete": WebhookDelete,
    "bot_commands_update": BotCommandsUpdate,
    "bot_commands_delete": BotCommandsDelete,
    "interaction_create": InteractionCreate,
    "feed_subscribe": FeedSubscribe,
    "feed_unsubscribe": FeedUnsubscribe,
    "notification_create": NotificationCreate,
}

# Known fields for each event type (event-specific, excluding base fields)
_KNOWN_FIELDS: dict[str, set[str]] = {}
for _name, _cls in _EVENT_MAP.items():
    _KNOWN_FIELDS[_name] = {
        f.name for f in _cls.__dataclass_fields__.values()
    } - {"type", "seq", "raw"}


def parse_event(raw: dict[str, Any]) -> GatewayEvent:
    """Parse a raw gateway message into a typed event dataclass."""
    event_type = raw.get("type", "")
    seq = raw.get("seq")
    data = raw.get("d", {}) or {}

    cls = _EVENT_MAP.get(event_type)
    if cls is None:
        return GatewayEvent(type=event_type, seq=seq, raw=raw)

    known = _KNOWN_FIELDS.get(event_type, set())
    kwargs: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for key, val in data.items():
        if key in known:
            kwargs[key] = val
        else:
            extra[key] = val

    # For events with an "extra" field, stuff unknown keys there
    if "extra" in {f.name for f in cls.__dataclass_fields__.values()}:
        kwargs["extra"] = extra

    # Special case: notification_create uses "type" in data for notification type
    if event_type == "notification_create" and "type" in data:
        kwargs["notification_type"] = data["type"]

    return cls(type=event_type, seq=seq, raw=raw, **kwargs)

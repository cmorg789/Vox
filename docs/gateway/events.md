# Events Reference

All server-to-client events dispatched over the gateway, organized by category.
Every event follows the standard message format:

```json
{
  "type": "event_name",
  "seq": 42,
  "d": { }
}
```

---

## Message Events

### message_create

Dispatched when a new message is sent to a feed or DM. The payload contains a
full `ChatMessage` object. For feeds the payload includes `feed_id`; for DMs it
includes `dm_id`. DM messages carry an `opaque_blob` field containing the E2EE
encrypted payload.

```json
{
  "type": "message_create",
  "seq": 10,
  "d": {
    "id": 1001,
    "feed_id": 500,
    "author_id": 100,
    "content": "Hello, world!",
    "attachments": [],
    "embeds": [],
    "reactions": [],
    "created_at": "2026-02-19T12:00:00Z"
  }
}
```

DM variant:

```json
{
  "type": "message_create",
  "seq": 11,
  "d": {
    "id": 1002,
    "dm_id": 300,
    "author_id": 101,
    "opaque_blob": "base64-e2ee-encrypted-payload",
    "created_at": "2026-02-19T12:00:05Z"
  }
}
```

### message_update

Dispatched when a message is edited. Contains the full updated message object.

### message_delete

Dispatched when a single message is deleted.

```json
{
  "d": {
    "id": 1001,
    "feed_id": 500
  }
}
```

### message_bulk_delete

Dispatched when multiple messages are deleted at once.

```json
{
  "d": {
    "ids": [1001, 1002, 1003],
    "feed_id": 500
  }
}
```

### message_reaction_add

Dispatched when a reaction is added to a message.

```json
{
  "d": {
    "message_id": 1001,
    "feed_id": 500,
    "user_id": 100,
    "emoji": "thumbsup"
  }
}
```

### message_reaction_remove

Dispatched when a reaction is removed from a message. Same shape as
`message_reaction_add`.

### message_pin_update

Dispatched when a message is pinned or unpinned.

```json
{
  "d": {
    "message_id": 1001,
    "feed_id": 500,
    "pinned": true
  }
}
```

---

## Member Events

### member_join

A user has joined the server.

```json
{
  "d": {
    "user_id": 100,
    "display_name": "alice",
    "joined_at": "2026-02-19T12:00:00Z"
  }
}
```

### member_leave

A user has left or been removed from the server.

```json
{
  "d": {
    "user_id": 100
  }
}
```

### member_update

A member's server-specific profile has changed (nickname, roles, etc.).

### member_ban

A member has been banned from the server.

```json
{
  "d": {
    "user_id": 100,
    "reason": "Spam"
  }
}
```

### member_unban

A previously banned user has been unbanned.

---

## Server Structure Events

### feed_create / feed_update / feed_delete

A text feed (channel) was created, updated, or deleted.

### room_create / room_update / room_delete

A voice/video room was created, updated, or deleted.

### category_create / category_update / category_delete

A category (group of feeds/rooms) was created, updated, or deleted.

### thread_create / thread_update / thread_delete

A thread within a feed was created, updated, or deleted.

### role_create / role_update / role_delete

A role was created, updated, or deleted.

### role_assign

A role was assigned to a member.

```json
{
  "d": {
    "user_id": 100,
    "role_id": 50
  }
}
```

### role_revoke

A role was removed from a member. Same shape as `role_assign`.

### server_update

Server-level settings have changed (name, icon, description, etc.).

### invite_create / invite_delete

An invite link was created or deleted.

### sticker_create / sticker_delete

A custom sticker was added to or removed from the server.

### emoji_create / emoji_delete

A custom emoji was added to or removed from the server.

### webhook_create / webhook_update / webhook_delete

A webhook was created, updated, or deleted.

### permission_override_update / permission_override_delete

A permission override on a feed, room, or category was updated or deleted.

### feed_subscribe / feed_unsubscribe

The current user subscribed to or unsubscribed from a feed for notifications.

### thread_subscribe / thread_unsubscribe

The current user subscribed to or unsubscribed from a thread.

### user_update

The current user's own profile was updated.

---

## Presence Events

### presence_update

A user's online status or activity changed.

```json
{
  "d": {
    "user_id": 100,
    "status": "idle",
    "custom_status": "Away for lunch",
    "activity": null
  }
}
```

### typing_start

A user started typing in a feed or DM.

```json
{
  "d": {
    "user_id": 100,
    "feed_id": 500
  }
}
```

---

## Voice Events

### voice_state_update

A user's voice state changed (join, leave, mute, deaf, video, streaming).

```json
{
  "d": {
    "user_id": 100,
    "room_id": 800,
    "self_mute": false,
    "self_deaf": false,
    "video": true,
    "streaming": false
  }
}
```

### voice_codec_neg

Server relays codec negotiation parameters from another participant.

### stage_request

A user requested to speak on a stage.

```json
{
  "d": {
    "user_id": 100,
    "room_id": 800
  }
}
```

### stage_invite

A moderator invited a user to speak on a stage.

### stage_invite_decline

A user declined a stage invite.

### stage_revoke

A user's speaking permission on a stage was revoked.

### stage_topic_update

The stage topic was changed.

```json
{
  "d": {
    "room_id": 800,
    "topic": "Q&A Session"
  }
}
```

### media_token_refresh

The server is providing a refreshed media authentication token for the SFU.

```json
{
  "d": {
    "token": "new-media-token",
    "expires_at": "2026-02-19T13:00:00Z"
  }
}
```

---

## DM Events

### dm_create

A new DM conversation was created.

### dm_update

A DM conversation was updated (e.g., group DM name change).

### dm_recipient_add

A user was added to a group DM.

### dm_recipient_remove

A user was removed from a group DM.

### dm_read_notify

Notifies that a DM has been read up to a certain message.

```json
{
  "d": {
    "dm_id": 300,
    "user_id": 101,
    "last_read_id": 1050
  }
}
```

---

## Social Events

### friend_request

A friend request was sent or received.

```json
{
  "d": {
    "from_user_id": 100,
    "to_user_id": 101
  }
}
```

### friend_remove

A friend was removed from the user's friend list.

### block_add

A user was blocked.

### block_remove

A user was unblocked.

---

## E2EE Events

### mls_welcome

An MLS Welcome message for the client to join an E2EE group.

### mls_commit

An MLS Commit message updating the group state.

### mls_proposal

An MLS Proposal message (add, remove, update).

### device_list_update

A user's device list has changed (new device added or device removed).

### device_pair_prompt

A prompt to pair a new device using CPace.

### cpace_isi

CPace initiator's first message (Initiator Sends ISI).

### cpace_rsi

CPace responder's reply (Responder Sends RSI).

### cpace_confirm

CPace pairing confirmation.

### cpace_new_device_key

A newly paired device's public key.

### key_reset_notify

Notification that a user has reset their E2EE keys. Clients should treat this
as a trust change and re-verify the user's identity.

---

## Bot Events

### interaction_create

A user invoked a bot command or interacted with a bot component.

```json
{
  "d": {
    "interaction_id": 9001,
    "bot_id": 200,
    "user_id": 100,
    "feed_id": 500,
    "command": "roll",
    "options": {
      "sides": 20
    }
  }
}
```

### bot_commands_update

A bot's command list was updated.

### bot_commands_delete

A bot's commands were removed (bot was removed from the server).

---

## Notification Events

### notification_create

A notification was generated for the current user.

```json
{
  "d": {
    "type": "mention",
    "msg_id": 1001,
    "feed_id": 500,
    "author_id": 101,
    "body_preview": "Hey @alice, check this out!"
  }
}
```

| Field          | Type   | Description                                               |
|----------------|--------|-----------------------------------------------------------|
| `type`         | string | One of `mention`, `reply`, `reaction`, `message`.         |
| `msg_id`       | int    | The message that triggered the notification.              |
| `feed_id`      | int    | Present for feed messages.                                |
| `dm_id`        | int    | Present for DM messages.                                  |
| `author_id`    | int    | The user who caused the notification.                     |
| `body_preview` | string | A short preview of the message body.                      |

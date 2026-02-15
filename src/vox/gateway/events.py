"""Typed event constructors for gateway events.

Each function returns a dict with {"type": ..., "d": {...}}.
The Connection adds "seq" when sending to clients.
"""

from __future__ import annotations

from typing import Any


def _event(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "d": data}


# --- Control ---

def hello(heartbeat_interval: int) -> dict[str, Any]:
    return _event("hello", {"heartbeat_interval": heartbeat_interval})


def heartbeat_ack() -> dict[str, Any]:
    return {"type": "heartbeat_ack"}


def ready(
    session_id: str,
    user_id: int,
    display_name: str,
    server_name: str,
    protocol_version: int = 1,
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    return _event("ready", {
        "session_id": session_id,
        "user_id": user_id,
        "display_name": display_name,
        "server_name": server_name,
        "protocol_version": protocol_version,
        "capabilities": capabilities or ["voice", "e2ee", "federation", "bots", "webhooks"],
    })


# --- Message Events ---

def message_create(
    msg_id: int, feed_id: int | None = None, dm_id: int | None = None,
    author_id: int = 0, body: str | None = None, timestamp: int = 0,
    reply_to: int | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {"msg_id": msg_id, "author_id": author_id, "body": body, "timestamp": timestamp}
    if feed_id is not None:
        d["feed_id"] = feed_id
    if dm_id is not None:
        d["dm_id"] = dm_id
    if reply_to is not None:
        d["reply_to"] = reply_to
    return _event("message_create", d)


def message_update(
    msg_id: int, feed_id: int | None = None, dm_id: int | None = None,
    body: str | None = None, edit_timestamp: int | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {"msg_id": msg_id}
    if feed_id is not None:
        d["feed_id"] = feed_id
    if dm_id is not None:
        d["dm_id"] = dm_id
    if body is not None:
        d["body"] = body
    if edit_timestamp is not None:
        d["edit_timestamp"] = edit_timestamp
    return _event("message_update", d)


def message_delete(msg_id: int, feed_id: int | None = None, dm_id: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"msg_id": msg_id}
    if feed_id is not None:
        d["feed_id"] = feed_id
    if dm_id is not None:
        d["dm_id"] = dm_id
    return _event("message_delete", d)


def message_bulk_delete(feed_id: int, msg_ids: list[int]) -> dict[str, Any]:
    return _event("message_bulk_delete", {"feed_id": feed_id, "msg_ids": msg_ids})


def message_reaction_add(msg_id: int, user_id: int, emoji: str) -> dict[str, Any]:
    return _event("message_reaction_add", {"msg_id": msg_id, "user_id": user_id, "emoji": emoji})


def message_reaction_remove(msg_id: int, user_id: int, emoji: str) -> dict[str, Any]:
    return _event("message_reaction_remove", {"msg_id": msg_id, "user_id": user_id, "emoji": emoji})


def message_pin_update(msg_id: int, feed_id: int, pinned: bool) -> dict[str, Any]:
    return _event("message_pin_update", {"msg_id": msg_id, "feed_id": feed_id, "pinned": pinned})


# --- Member Events ---

def member_join(user_id: int, display_name: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"user_id": user_id}
    if display_name is not None:
        d["display_name"] = display_name
    return _event("member_join", d)


def member_leave(user_id: int) -> dict[str, Any]:
    return _event("member_leave", {"user_id": user_id})


def member_update(user_id: int, nickname: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"user_id": user_id}
    if nickname is not None:
        d["nickname"] = nickname
    return _event("member_update", d)


def member_ban(user_id: int) -> dict[str, Any]:
    return _event("member_ban", {"user_id": user_id})


def member_unban(user_id: int) -> dict[str, Any]:
    return _event("member_unban", {"user_id": user_id})


# --- Channel Events ---

def feed_create(feed_id: int, name: str, type: str | None = None, topic: str | None = None, category_id: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"feed_id": feed_id, "name": name}
    if type is not None:
        d["type"] = type
    if topic is not None:
        d["topic"] = topic
    if category_id is not None:
        d["category_id"] = category_id
    return _event("feed_create", d)


def feed_update(feed_id: int, **changed: Any) -> dict[str, Any]:
    return _event("feed_update", {"feed_id": feed_id, **changed})


def feed_delete(feed_id: int) -> dict[str, Any]:
    return _event("feed_delete", {"feed_id": feed_id})


def room_create(room_id: int, name: str, type: str | None = None, category_id: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"room_id": room_id, "name": name}
    if type is not None:
        d["type"] = type
    if category_id is not None:
        d["category_id"] = category_id
    return _event("room_create", d)


def room_update(room_id: int, **changed: Any) -> dict[str, Any]:
    return _event("room_update", {"room_id": room_id, **changed})


def room_delete(room_id: int) -> dict[str, Any]:
    return _event("room_delete", {"room_id": room_id})


def category_create(category_id: int, name: str, position: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"category_id": category_id, "name": name}
    if position is not None:
        d["position"] = position
    return _event("category_create", d)


def category_update(category_id: int, **changed: Any) -> dict[str, Any]:
    return _event("category_update", {"category_id": category_id, **changed})


def category_delete(category_id: int) -> dict[str, Any]:
    return _event("category_delete", {"category_id": category_id})


def thread_create(thread_id: int, parent_feed_id: int, name: str, parent_msg_id: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"thread_id": thread_id, "parent_feed_id": parent_feed_id, "name": name}
    if parent_msg_id is not None:
        d["parent_msg_id"] = parent_msg_id
    return _event("thread_create", d)


def thread_update(thread_id: int, **changed: Any) -> dict[str, Any]:
    return _event("thread_update", {"thread_id": thread_id, **changed})


def thread_delete(thread_id: int) -> dict[str, Any]:
    return _event("thread_delete", {"thread_id": thread_id})


# --- Role Events ---

def role_create(role_id: int, name: str, color: str | None = None, permissions: int = 0, position: int = 0) -> dict[str, Any]:
    return _event("role_create", {"role_id": role_id, "name": name, "color": color, "permissions": permissions, "position": position})


def role_update(role_id: int, **changed: Any) -> dict[str, Any]:
    return _event("role_update", {"role_id": role_id, **changed})


def role_delete(role_id: int) -> dict[str, Any]:
    return _event("role_delete", {"role_id": role_id})


# --- Server Events ---

def server_update(**changed: Any) -> dict[str, Any]:
    return _event("server_update", changed)


# --- Invite Events ---

def invite_create(code: str, creator_id: int, feed_id: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"code": code, "creator_id": creator_id}
    if feed_id is not None:
        d["feed_id"] = feed_id
    return _event("invite_create", d)


def invite_delete(code: str) -> dict[str, Any]:
    return _event("invite_delete", {"code": code})


# --- DM Events ---

def dm_create(dm_id: int, participant_ids: list[int], is_group: bool = False, name: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"dm_id": dm_id, "participant_ids": participant_ids, "is_group": is_group}
    if name is not None:
        d["name"] = name
    return _event("dm_create", d)


def dm_update(dm_id: int, **changed: Any) -> dict[str, Any]:
    return _event("dm_update", {"dm_id": dm_id, **changed})


def dm_recipient_add(dm_id: int, user_id: int) -> dict[str, Any]:
    return _event("dm_recipient_add", {"dm_id": dm_id, "user_id": user_id})


def dm_recipient_remove(dm_id: int, user_id: int) -> dict[str, Any]:
    return _event("dm_recipient_remove", {"dm_id": dm_id, "user_id": user_id})


def dm_read_notify(dm_id: int, user_id: int, up_to_msg_id: int) -> dict[str, Any]:
    return _event("dm_read_notify", {"dm_id": dm_id, "user_id": user_id, "up_to_msg_id": up_to_msg_id})


# --- Presence Events ---

def typing_start(user_id: int, feed_id: int | None = None, dm_id: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"user_id": user_id}
    if feed_id is not None:
        d["feed_id"] = feed_id
    if dm_id is not None:
        d["dm_id"] = dm_id
    return _event("typing_start", d)


def presence_update(user_id: int, status: str, **extra: Any) -> dict[str, Any]:
    return _event("presence_update", {"user_id": user_id, "status": status, **extra})

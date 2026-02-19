"""Tests for the gateway client and event parsing."""

import asyncio
import json

import pytest

from vox_sdk.errors import VoxGatewayError
from vox_sdk.models.events import (
    GatewayEvent,
    Hello,
    MessageCreate,
    Ready,
    FeedUpdate,
    NotificationCreate,
    parse_event,
)


class TestParseEvent:
    def test_hello(self):
        raw = {"type": "hello", "d": {"heartbeat_interval": 45000}}
        event = parse_event(raw)
        assert isinstance(event, Hello)
        assert event.heartbeat_interval == 45000

    def test_ready(self):
        raw = {
            "type": "ready",
            "seq": 1,
            "d": {
                "session_id": "sess_abc",
                "user_id": 42,
                "display_name": "Alice",
                "server_name": "Test",
                "protocol_version": 1,
                "capabilities": ["voice", "e2ee"],
            },
        }
        event = parse_event(raw)
        assert isinstance(event, Ready)
        assert event.session_id == "sess_abc"
        assert event.user_id == 42
        assert event.seq == 1
        assert event.capabilities == ["voice", "e2ee"]

    def test_message_create(self):
        raw = {
            "type": "message_create",
            "seq": 5,
            "d": {
                "msg_id": 100,
                "feed_id": 1,
                "author_id": 42,
                "body": "Hello world",
                "timestamp": 1700000000,
            },
        }
        event = parse_event(raw)
        assert isinstance(event, MessageCreate)
        assert event.msg_id == 100
        assert event.body == "Hello world"
        assert event.feed_id == 1

    def test_unknown_event(self):
        raw = {"type": "some_future_event", "d": {"foo": "bar"}}
        event = parse_event(raw)
        assert isinstance(event, GatewayEvent)
        assert event.type == "some_future_event"
        assert event.raw == raw

    def test_event_with_extra_fields(self):
        raw = {
            "type": "feed_update",
            "seq": 3,
            "d": {"feed_id": 1, "name": "renamed", "topic": "new topic"},
        }
        event = parse_event(raw)
        assert isinstance(event, FeedUpdate)
        assert event.feed_id == 1
        assert event.extra == {"name": "renamed", "topic": "new topic"}

    def test_notification_create_type_mapping(self):
        raw = {
            "type": "notification_create",
            "seq": 10,
            "d": {
                "user_id": 1,
                "type": "mention",
                "feed_id": 5,
                "msg_id": 100,
                "actor_id": 2,
                "body_preview": "hey @you",
            },
        }
        event = parse_event(raw)
        assert isinstance(event, NotificationCreate)
        assert event.notification_type == "mention"
        assert event.user_id == 1


class TestVoxGatewayError:
    def test_can_resume(self):
        err = VoxGatewayError(4007, "SESSION_TIMEOUT")
        assert err.can_resume is True
        assert err.can_reconnect is True

    def test_cannot_resume_auth_failed(self):
        err = VoxGatewayError(4004, "AUTH_FAILED")
        assert err.can_resume is False
        assert err.can_reconnect is False

    def test_can_reconnect_not_resume(self):
        err = VoxGatewayError(4009, "SESSION_EXPIRED")
        assert err.can_resume is False
        assert err.can_reconnect is True

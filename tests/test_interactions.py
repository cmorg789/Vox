"""Tests for the ephemeral in-memory interaction store."""

import time as _time

from vox.interactions import INTERACTION_TTL, Interaction, _store, consume, create, get, reset


def test_create_returns_interaction_with_fields():
    ix = create(type="slash_command", command="/ping", params={"a": 1}, user_id=1, feed_id=10, dm_id=None, bot_id=99)
    assert isinstance(ix, Interaction)
    assert ix.type == "slash_command"
    assert ix.command == "/ping"
    assert ix.params == {"a": 1}
    assert ix.user_id == 1
    assert ix.feed_id == 10
    assert ix.dm_id is None
    assert ix.bot_id == 99
    assert isinstance(ix.id, str)
    assert isinstance(ix.created_at, float)


def test_create_stores_in_store():
    ix = create(type="button", command=None, params={}, user_id=2, feed_id=None, dm_id=5, bot_id=10)
    assert ix.id in _store
    assert _store[ix.id] is ix


def test_create_generates_unique_ids():
    a = create(type="button", command=None, params={}, user_id=1, feed_id=None, dm_id=None, bot_id=1)
    b = create(type="button", command=None, params={}, user_id=1, feed_id=None, dm_id=None, bot_id=1)
    assert a.id != b.id


def test_get_returns_interaction():
    ix = create(type="slash_command", command="/help", params={}, user_id=1, feed_id=1, dm_id=None, bot_id=1)
    result = get(ix.id)
    assert result is ix


def test_get_returns_none_for_unknown_id():
    assert get("nonexistent_id") is None


def test_get_returns_none_after_ttl_expired(monkeypatch):
    ix = create(type="button", command=None, params={}, user_id=1, feed_id=None, dm_id=None, bot_id=1)
    future = ix.created_at + INTERACTION_TTL + 1
    monkeypatch.setattr(_time, "time", lambda: future)
    assert get(ix.id) is None
    assert ix.id not in _store


def test_get_returns_interaction_within_ttl(monkeypatch):
    ix = create(type="button", command=None, params={}, user_id=1, feed_id=None, dm_id=None, bot_id=1)
    just_before = ix.created_at + INTERACTION_TTL - 0.5
    monkeypatch.setattr(_time, "time", lambda: just_before)
    assert get(ix.id) is ix


def test_consume_returns_and_removes():
    ix = create(type="slash_command", command="/roll", params={}, user_id=1, feed_id=1, dm_id=None, bot_id=1)
    result = consume(ix.id)
    assert result is ix
    assert ix.id not in _store


def test_consume_returns_none_for_unknown():
    assert consume("nonexistent") is None


def test_consume_returns_none_after_ttl(monkeypatch):
    ix = create(type="button", command=None, params={}, user_id=1, feed_id=None, dm_id=None, bot_id=1)
    future = ix.created_at + INTERACTION_TTL + 1
    monkeypatch.setattr(_time, "time", lambda: future)
    assert consume(ix.id) is None


def test_reset_clears_all():
    create(type="button", command=None, params={}, user_id=1, feed_id=None, dm_id=None, bot_id=1)
    create(type="button", command=None, params={}, user_id=2, feed_id=None, dm_id=None, bot_id=2)
    assert len(_store) >= 2
    reset()
    assert len(_store) == 0

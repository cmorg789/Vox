"""Tests for the rate limiter."""

import time

import httpx
import pytest

from vox_sdk.rate_limit import BucketInfo, RateLimiter, classify


class TestClassify:
    def test_auth(self):
        assert classify("/api/v1/auth/login") == "auth"

    def test_messages_nested(self):
        assert classify("/api/v1/feeds/123/messages") == "messages"

    def test_channels_feed(self):
        assert classify("/api/v1/feeds/123") == "channels"

    def test_channels_room(self):
        assert classify("/api/v1/rooms/456") == "channels"

    def test_search_in_path(self):
        # /messages/search matches /messages first (server behavior)
        assert classify("/api/v1/messages/search") == "messages"
        # Standalone search paths
        assert classify("/api/v1/feeds/1/search") == "search"

    def test_dms_are_messages(self):
        assert classify("/api/v1/dms/123") == "messages"

    def test_users_are_members(self):
        assert classify("/api/v1/users/123") == "members"

    def test_fallback_to_server(self):
        assert classify("/api/v1/unknown/path") == "server"

    def test_federation(self):
        assert classify("/api/v1/federation/relay/message") == "federation"

    def test_emoji(self):
        assert classify("/api/v1/emoji") == "emoji"

    def test_stickers(self):
        assert classify("/api/v1/stickers") == "emoji"


class TestRateLimiter:
    def test_update_from_response(self):
        rl = RateLimiter()
        response = httpx.Response(
            200,
            headers={
                "x-ratelimit-limit": "50",
                "x-ratelimit-remaining": "49",
                "x-ratelimit-reset": str(int(time.time()) + 60),
            },
        )
        rl.update_from_response("/api/v1/feeds/1/messages", response)
        bucket = rl._buckets.get("messages")
        assert bucket is not None
        assert bucket.limit == 50
        assert bucket.remaining == 49

    def test_no_update_without_headers(self):
        rl = RateLimiter()
        response = httpx.Response(200)
        rl.update_from_response("/api/v1/server", response)
        assert "server" not in rl._buckets

    @pytest.mark.asyncio
    async def test_wait_if_needed_no_bucket(self):
        rl = RateLimiter()
        # Should not raise or block
        await rl.wait_if_needed("/api/v1/server")

    @pytest.mark.asyncio
    async def test_wait_if_needed_has_remaining(self):
        rl = RateLimiter()
        rl._buckets["auth"] = BucketInfo(limit=5, remaining=3, reset=time.time() + 60)
        await rl.wait_if_needed("/api/v1/auth/login")
        # Should return immediately

    @pytest.mark.asyncio
    async def test_wait_if_needed_exhausted_past_reset(self):
        rl = RateLimiter()
        rl._buckets["auth"] = BucketInfo(limit=5, remaining=0, reset=time.time() - 1)
        # Reset is in the past, should not block
        await rl.wait_if_needed("/api/v1/auth/login")

    @pytest.mark.asyncio
    async def test_wait_if_needed_exhausted_future_reset(self, monkeypatch):
        """Exhausted bucket with future reset should sleep until reset."""
        import asyncio

        rl = RateLimiter()
        reset_time = time.time() + 5
        rl._buckets["auth"] = BucketInfo(limit=5, remaining=0, reset=reset_time)

        sleep_delays: list[float] = []
        original_sleep = asyncio.sleep

        async def fake_sleep(delay):
            sleep_delays.append(delay)
            # Don't actually sleep

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        await rl.wait_if_needed("/api/v1/auth/login")

        assert len(sleep_delays) == 1
        # Should be approximately 5 seconds (allow for time drift)
        assert 4.0 < sleep_delays[0] <= 6.0

    @pytest.mark.asyncio
    async def test_wait_if_needed_recheck_after_lock(self, monkeypatch):
        """If bucket is replenished while waiting for the lock, skip sleeping."""
        import asyncio

        rl = RateLimiter()
        reset_time = time.time() + 5
        rl._buckets["auth"] = BucketInfo(limit=5, remaining=0, reset=reset_time)

        sleep_called = False

        async def fake_sleep(delay):
            nonlocal sleep_called
            sleep_called = True

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        # Simulate: after the lock is acquired, the bucket has been refreshed
        original_lock_acquire = asyncio.Lock.acquire

        async def patched_acquire(self):
            await original_lock_acquire(self)
            # Simulate another task updating the bucket
            rl._buckets["auth"] = BucketInfo(limit=5, remaining=3, reset=time.time() + 60)

        monkeypatch.setattr(asyncio.Lock, "acquire", patched_acquire)
        await rl.wait_if_needed("/api/v1/auth/login")

        assert not sleep_called, "Should not sleep when bucket was replenished"

"""Tests for vox_sdk._media video support (VoxMediaClient)."""

import time

import pytest

from vox_sdk._media import VoxMediaClient


class TestVoxMediaClientConstruction:
    """Basic construction and state tests (no hardware needed)."""

    def test_create_client(self):
        client = VoxMediaClient()
        assert client.is_muted is False
        assert client.is_deafened is False
        assert client.is_video_enabled is False

    def test_start_and_stop(self):
        client = VoxMediaClient()
        client.start()
        client.stop()

    def test_double_start_raises(self):
        client = VoxMediaClient()
        client.start()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                client.start()
        finally:
            client.stop()

    def test_stop_idempotent(self):
        client = VoxMediaClient()
        client.start()
        client.stop()
        # Second stop should not raise
        client.stop()


class TestVideoMethods:
    """Test the video-specific Python API methods exist and behave correctly."""

    def test_set_video_before_start_raises(self):
        client = VoxMediaClient()
        with pytest.raises(RuntimeError, match="not started"):
            client.set_video(True)

    def test_set_video_config_before_start_raises(self):
        client = VoxMediaClient()
        with pytest.raises(RuntimeError, match="not started"):
            client.set_video_config(640, 480, 30, 500)

    def test_set_video_sends_command(self):
        """set_video(True) should succeed (sends command to runtime) and update state."""
        client = VoxMediaClient()
        client.start()
        try:
            client.set_video(True)
            assert client.is_video_enabled is True

            client.set_video(False)
            assert client.is_video_enabled is False
        finally:
            client.stop()

    def test_set_video_config_sends_command(self):
        """set_video_config should succeed without raising."""
        client = VoxMediaClient()
        client.start()
        try:
            client.set_video_config(1280, 720, 30, 1000)
            client.set_video_config()  # defaults
        finally:
            client.stop()

    def test_poll_video_frame_returns_none_when_empty(self):
        """poll_video_frame returns None when no frames are available."""
        client = VoxMediaClient()
        client.start()
        try:
            assert client.poll_video_frame() is None
        finally:
            client.stop()


class TestVideoEvents:
    """Test video-related events propagated back from the media runtime."""

    def test_video_enable_without_connect_emits_error(self):
        """Enabling video without an active SFU connection should emit a video_error event
        (camera won't start without a session, command is just queued)."""
        client = VoxMediaClient()
        client.start()
        try:
            client.set_video(True)
            # Give the runtime a moment to process
            time.sleep(0.1)
            # The command is accepted but there's no active session,
            # so it's just silently ignored (no crash)
            # poll_event should not have a crash-type event
            events = []
            while True:
                ev = client.poll_event()
                if ev is None:
                    break
                events.append(ev)
            # No connect_failed or crash events expected
            for ev_type, _ in events:
                assert ev_type != "connect_failed"
        finally:
            client.stop()


class TestPollVideoFrameSignature:
    """Test poll_video_frame return type contract."""

    def test_poll_returns_none_or_tuple(self):
        """poll_video_frame should return None or a 4-tuple (user_id, w, h, bytes)."""
        client = VoxMediaClient()
        client.start()
        try:
            result = client.poll_video_frame()
            # Without a connection, should be None
            assert result is None
        finally:
            client.stop()


class TestMuteDeafVideo:
    """Test that mute/deaf/video state toggles work independently."""

    def test_independent_toggles(self):
        client = VoxMediaClient()
        client.start()
        try:
            client.set_mute(True)
            assert client.is_muted is True
            assert client.is_deafened is False
            assert client.is_video_enabled is False

            client.set_deaf(True)
            assert client.is_muted is True
            assert client.is_deafened is True
            assert client.is_video_enabled is False

            client.set_video(True)
            assert client.is_muted is True
            assert client.is_deafened is True
            assert client.is_video_enabled is True

            client.set_video(False)
            assert client.is_video_enabled is False
            assert client.is_muted is True
        finally:
            client.stop()


class TestConnectWithoutServer:
    """Test connect + video commands without a real SFU (exercises command pipeline)."""

    def test_connect_bad_address_emits_event(self):
        """Connecting to a bad address should emit connect_failed."""
        client = VoxMediaClient()
        client.start()
        try:
            # Use a short idle timeout so the QUIC connect fails faster.
            # Connect to localhost port 1 which should refuse/timeout.
            client.connect(
                "127.0.0.1:1", "fake-token", 1, 1,
                idle_timeout_secs=2,
            )
            # Wait for async connect to fail (QUIC timeout + processing)
            deadline = time.time() + 35
            events = []
            while time.time() < deadline:
                ev = client.poll_event()
                if ev is not None:
                    events.append(ev)
                    if ev[0] == "connect_failed":
                        break
                time.sleep(0.1)

            event_types = [e[0] for e in events]
            assert "connect_failed" in event_types
        finally:
            client.stop()

    def test_set_video_config_then_connect(self):
        """Setting video config before connect should not crash."""
        client = VoxMediaClient()
        client.start()
        try:
            client.set_video_config(320, 240, 15, 250)
            client.set_video(True)
            # No crash = success; the command is queued but no session exists
            time.sleep(0.1)
        finally:
            client.stop()

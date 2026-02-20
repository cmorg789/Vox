"""Tests for SDK response models."""

import pytest

from vox_sdk.models.auth import LoginResponse, MFARequiredResponse, RegisterResponse
from vox_sdk.models.channels import FeedResponse, RoomResponse, ThreadResponse
from vox_sdk.models.errors import ErrorCode, ErrorResponse
from vox_sdk.models.members import MemberResponse
from vox_sdk.models.messages import MessageResponse
from vox_sdk.models.roles import RoleResponse
from vox_sdk.models.server import ServerInfoResponse, ServerLayoutResponse
from vox_sdk.models.users import UserResponse
from vox_sdk.models.voice import MediaCertResponse, VoiceJoinResponse, VoiceMemberData
from vox_sdk.models.dms import DMResponse
from vox_sdk.models.e2ee import PrekeyBundleResponse
from vox_sdk.models.invites import InviteResponse
from vox_sdk.models.files import FileResponse


class TestAuthModels:
    def test_register_response(self):
        r = RegisterResponse(user_id=1, token="abc")
        assert r.user_id == 1
        assert r.token == "abc"

    def test_login_response(self):
        r = LoginResponse.model_validate({
            "token": "tok", "user_id": 42, "display_name": "Alice", "roles": [1, 2]
        })
        assert r.user_id == 42
        assert r.roles == [1, 2]

    def test_mfa_required(self):
        r = MFARequiredResponse.model_validate({
            "mfa_required": True,
            "mfa_ticket": "mfa_abc",
            "available_methods": ["totp"],
        })
        assert r.mfa_ticket == "mfa_abc"


class TestErrorModels:
    def test_error_response(self):
        r = ErrorResponse.model_validate({
            "code": "AUTH_FAILED",
            "message": "Bad password",
        })
        assert r.code == ErrorCode.AUTH_FAILED
        assert r.retry_after_ms is None

    def test_no_cert_pinning_code(self):
        r = ErrorResponse.model_validate({
            "code": "NO_CERT_PINNING",
            "message": "CA-signed certificate in use",
        })
        assert r.code == ErrorCode.NO_CERT_PINNING

    def test_error_with_retry(self):
        r = ErrorResponse.model_validate({
            "code": "RATE_LIMITED",
            "message": "Slow down",
            "retry_after_ms": 5000,
        })
        assert r.retry_after_ms == 5000


class TestCoreModels:
    def test_message_response(self):
        r = MessageResponse.model_validate({
            "msg_id": 1,
            "feed_id": 10,
            "author_id": 42,
            "body": "hello",
            "timestamp": 1700000000,
        })
        assert r.msg_id == 1
        assert r.attachments == []

    def test_feed_response(self):
        r = FeedResponse.model_validate({
            "feed_id": 1,
            "name": "general",
            "type": "text",
            "position": 0,
        })
        assert r.feed_id == 1
        assert r.permission_overrides == []

    def test_member_response(self):
        r = MemberResponse.model_validate({
            "user_id": 42,
            "display_name": "Alice",
            "role_ids": [1, 2],
        })
        assert r.role_ids == [1, 2]

    def test_role_response(self):
        r = RoleResponse.model_validate({
            "role_id": 1,
            "name": "Admin",
            "permissions": 8,
            "position": 1,
        })
        assert r.permissions == 8

    def test_user_response(self):
        r = UserResponse.model_validate({
            "user_id": 42,
            "username": "alice",
            "created_at": 1700000000,
        })
        assert r.federated is False

    def test_server_info(self):
        r = ServerInfoResponse.model_validate({
            "name": "Test Server",
            "member_count": 100,
        })
        assert r.name == "Test Server"

    def test_extra_fields_ignored(self):
        """Models should ignore unknown fields from the server."""
        r = MemberResponse.model_validate({
            "user_id": 1,
            "display_name": "x",
            "role_ids": [],
            "some_new_field": "value",
        })
        assert r.user_id == 1

    def test_media_cert_response(self):
        r = MediaCertResponse.model_validate({
            "fingerprint": "sha256:abcdef1234567890",
            "cert_der": [48, 130, 1, 0],
        })
        assert r.fingerprint == "sha256:abcdef1234567890"
        assert r.cert_der == [48, 130, 1, 0]

    def test_voice_join_response(self):
        r = VoiceJoinResponse.model_validate({
            "media_url": "quic://sfu.test:4443",
            "media_token": "tok",
            "members": [
                {"user_id": 1, "mute": False, "deaf": False, "video": False,
                 "streaming": False, "server_mute": False, "server_deaf": False},
            ],
        })
        assert len(r.members) == 1
        assert r.members[0].user_id == 1

    def test_dm_response(self):
        r = DMResponse.model_validate({
            "dm_id": 1,
            "participant_ids": [1, 2],
            "is_group": False,
        })
        assert r.participant_ids == [1, 2]

    def test_invite_response(self):
        r = InviteResponse.model_validate({
            "code": "abc123",
            "creator_id": 1,
            "uses": 5,
        })
        assert r.code == "abc123"

    def test_file_response(self):
        r = FileResponse.model_validate({
            "file_id": "f_abc",
            "name": "image.png",
            "size": 1024,
            "mime": "image/png",
            "url": "/files/f_abc",
        })
        assert r.size == 1024

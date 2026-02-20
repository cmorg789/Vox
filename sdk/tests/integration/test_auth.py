"""SDK integration tests for authentication endpoints."""

import pyotp
import pytest

from vox_sdk import VoxHTTPError
from vox_sdk.models.auth import RegisterResponse

from .conftest import register

pytestmark = pytest.mark.anyio


class TestAuth:
    async def test_register_returns_model(self, sdk):
        resp = await sdk.auth.register("alice", "password123")
        assert isinstance(resp, RegisterResponse)
        assert resp.user_id > 0
        assert isinstance(resp.token, str) and len(resp.token) > 0

    async def test_login_sets_token(self, sdk):
        await register(sdk, "alice", "password123")
        sdk.http.token = None
        result = await sdk.login("alice", "password123")
        assert sdk.http.token == result.token
        # Authenticated call should work
        await sdk.members.list()

    async def test_logout_invalidates(self, sdk):
        await register(sdk, "alice", "password123")
        original_token = sdk.http.token
        await sdk.auth.logout()
        # Reuse the original token — the server should have deleted the session
        sdk.http.token = original_token
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.members.list()
        assert exc_info.value.status == 401

    async def test_mfa_totp_lifecycle(self, sdk):
        await register(sdk, "alice", "password123")

        # MFA should be disabled initially
        status = await sdk.auth.mfa_status()
        assert status.totp_enabled is False

        # Begin TOTP setup
        setup = await sdk.auth.mfa_setup("totp")
        assert setup.method == "totp"
        assert setup.totp_secret is not None
        assert setup.setup_id

        # Generate a valid TOTP code from the secret
        totp = pyotp.TOTP(setup.totp_secret)
        code = totp.now()

        # Confirm setup with the code
        confirm = await sdk.auth.mfa_setup_confirm(setup.setup_id, code=code)
        assert confirm.success is True
        assert len(confirm.recovery_codes) > 0

        # MFA should now be enabled
        status = await sdk.auth.mfa_status()
        assert status.totp_enabled is True
        assert status.recovery_codes_left > 0

        # Remove TOTP with a fresh code
        fresh_code = totp.now()
        result = await sdk.auth.mfa_remove("totp", code=fresh_code)
        assert result.success is True

        # MFA should be disabled again
        status = await sdk.auth.mfa_status()
        assert status.totp_enabled is False

    async def test_session_management(self, sdk):
        await register(sdk, "alice", "password123")

        sessions = await sdk.auth.list_sessions()
        assert len(sessions.sessions) >= 1
        current = sessions.sessions[0]
        assert current.session_id > 0
        assert current.created_at > 0

        # Revoke the current session
        await sdk.auth.revoke_session(current.session_id)

        # The token should now be invalid
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.auth.list_sessions()
        assert exc_info.value.status == 401

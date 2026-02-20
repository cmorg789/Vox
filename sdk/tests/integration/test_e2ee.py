"""SDK integration tests for E2EE (device & key) endpoints."""

import pytest

from vox_sdk import VoxHTTPError

from .conftest import register

pytestmark = pytest.mark.anyio


class TestE2EE:
    async def test_device_crud(self, sdk):
        """Add a device, list devices, remove it."""
        await register(sdk, "alice", "password123")

        added = await sdk.e2ee.add_device("dev-001", "Alice's Phone")
        assert added.device_id == "dev-001"

        devices = await sdk.e2ee.list_devices()
        assert any(d.device_id == "dev-001" for d in devices.devices)

        await sdk.e2ee.remove_device("dev-001")

        devices = await sdk.e2ee.list_devices()
        assert not any(d.device_id == "dev-001" for d in devices.devices)

    async def test_upload_and_get_prekeys(self, sdk):
        """Add device, upload prekeys, fetch prekey bundle for user."""
        reg = await register(sdk, "alice", "password123")

        await sdk.e2ee.add_device("dev-001", "Alice's Phone")
        await sdk.e2ee.upload_prekeys(
            device_id="dev-001",
            identity_key="ident-key-abc",
            signed_prekey="signed-pk-xyz",
            one_time_prekeys=["otpk-1", "otpk-2", "otpk-3"],
        )

        bundle = await sdk.e2ee.get_prekeys(reg.user_id)
        assert bundle.user_id == reg.user_id
        assert len(bundle.devices) >= 1
        dev = next(d for d in bundle.devices if d.device_id == "dev-001")
        assert dev.identity_key == "ident-key-abc"
        assert dev.signed_prekey == "signed-pk-xyz"
        assert dev.one_time_prekey is not None

    async def test_key_backup(self, sdk):
        """Upload encrypted key backup blob, download and verify."""
        await register(sdk, "alice", "password123")

        blob = "encrypted-backup-data-abc123"
        await sdk.e2ee.upload_key_backup(blob)

        backup = await sdk.e2ee.download_key_backup()
        assert backup.encrypted_blob == blob

    async def test_reset_keys(self, sdk):
        """Upload prekeys, reset, verify prekeys cleared."""
        reg = await register(sdk, "alice", "password123")

        await sdk.e2ee.add_device("dev-001", "Alice's Phone")
        await sdk.e2ee.upload_prekeys(
            device_id="dev-001",
            identity_key="ident-key-abc",
            signed_prekey="signed-pk-xyz",
            one_time_prekeys=["otpk-1"],
        )

        await sdk.e2ee.reset_keys()

        bundle = await sdk.e2ee.get_prekeys(reg.user_id)
        # After reset, the device's prekeys should be cleared
        if bundle.devices:
            dev = next((d for d in bundle.devices if d.device_id == "dev-001"), None)
            if dev is not None:
                assert dev.identity_key == "" or dev.one_time_prekey is None
        # Alternatively, the bundle may be empty after reset

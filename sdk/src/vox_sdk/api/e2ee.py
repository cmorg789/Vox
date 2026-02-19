"""E2EE API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.e2ee import (
    AddDeviceResponse,
    DeviceListResponse,
    KeyBackupResponse,
    PairDeviceResponse,
    PrekeyBundleResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class E2EEAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def upload_prekeys(
        self,
        device_id: str,
        identity_key: str,
        signed_prekey: str,
        one_time_prekeys: list[str],
    ) -> None:
        await self._http.put(
            f"/api/v1/keys/prekeys/{device_id}",
            json={
                "identity_key": identity_key,
                "signed_prekey": signed_prekey,
                "one_time_prekeys": one_time_prekeys,
            },
        )

    async def get_prekeys(self, user_id: int) -> PrekeyBundleResponse:
        r = await self._http.get(f"/api/v1/keys/prekeys/{user_id}")
        return PrekeyBundleResponse.model_validate(r.json())

    async def list_devices(self) -> DeviceListResponse:
        r = await self._http.get("/api/v1/keys/devices")
        return DeviceListResponse.model_validate(r.json())

    async def add_device(self, device_id: str, device_name: str) -> AddDeviceResponse:
        r = await self._http.post(
            "/api/v1/keys/devices",
            json={"device_id": device_id, "device_name": device_name},
        )
        return AddDeviceResponse.model_validate(r.json())

    async def remove_device(self, device_id: str) -> None:
        await self._http.delete(f"/api/v1/keys/devices/{device_id}")

    async def initiate_pairing(
        self,
        device_name: str,
        method: str,
        temp_public_key: str | None = None,
    ) -> PairDeviceResponse:
        payload: dict[str, Any] = {"device_name": device_name, "method": method}
        if temp_public_key is not None:
            payload["temp_public_key"] = temp_public_key
        r = await self._http.post("/api/v1/keys/devices/pair", json=payload)
        return PairDeviceResponse.model_validate(r.json())

    async def respond_to_pairing(self, pair_id: str, approved: bool) -> None:
        await self._http.post(
            f"/api/v1/keys/devices/pair/{pair_id}/respond",
            json={"approved": approved},
        )

    async def upload_key_backup(self, encrypted_blob: str) -> None:
        await self._http.put(
            "/api/v1/keys/backup", json={"encrypted_blob": encrypted_blob}
        )

    async def download_key_backup(self) -> KeyBackupResponse:
        r = await self._http.get("/api/v1/keys/backup")
        return KeyBackupResponse.model_validate(r.json())

    async def reset_keys(self) -> None:
        await self._http.post("/api/v1/keys/reset")

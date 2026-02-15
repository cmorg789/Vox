import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.db.models import Device, KeyBackup, OneTimePrekey, Prekey, User
from vox.models.e2ee import (
    AddDeviceRequest,
    DevicePrekey,
    KeyBackupRequest,
    KeyBackupResponse,
    PairDeviceRequest,
    PairDeviceResponse,
    PairRespondRequest,
    PrekeyBundleResponse,
    UploadPrekeysRequest,
)

router = APIRouter(prefix="/api/v1/keys", tags=["e2ee"])


@router.put("/prekeys", status_code=204)
async def upload_prekeys(
    body: UploadPrekeysRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Get user's first device (or require device_id in header later)
    result = await db.execute(select(Device).where(Device.user_id == user.id).limit(1))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "No device registered."}})

    # Upsert prekey
    result = await db.execute(select(Prekey).where(Prekey.device_id == device.id))
    existing = result.scalar_one_or_none()
    if existing:
        existing.identity_key = body.identity_key
        existing.signed_prekey = body.signed_prekey
    else:
        db.add(Prekey(device_id=device.id, identity_key=body.identity_key, signed_prekey=body.signed_prekey))

    # Add one-time prekeys
    for key_data in body.one_time_prekeys:
        db.add(OneTimePrekey(device_id=device.id, key_data=key_data))

    await db.commit()


@router.get("/prekeys/{user_id}")
async def get_prekey_bundle(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PrekeyBundleResponse:
    devices_result = await db.execute(select(Device).where(Device.user_id == user_id))
    devices = devices_result.scalars().all()

    bundles = []
    for dev in devices:
        prekey_result = await db.execute(select(Prekey).where(Prekey.device_id == dev.id))
        prekey = prekey_result.scalar_one_or_none()
        if prekey is None:
            continue

        # Pop one-time prekey
        otp_result = await db.execute(select(OneTimePrekey).where(OneTimePrekey.device_id == dev.id).limit(1))
        otp = otp_result.scalar_one_or_none()
        otp_key = None
        if otp:
            otp_key = otp.key_data
            await db.delete(otp)

        bundles.append(DevicePrekey(device_id=dev.id, identity_key=prekey.identity_key, signed_prekey=prekey.signed_prekey, one_time_prekey=otp_key))

    await db.commit()
    return PrekeyBundleResponse(user_id=user_id, devices=bundles)


@router.post("/devices", status_code=201)
async def add_device(
    body: AddDeviceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db.add(Device(id=body.device_id, user_id=user.id, device_name=body.device_name, created_at=datetime.now(timezone.utc)))
    await db.commit()
    return {"device_id": body.device_id}


@router.delete("/devices/{device_id}", status_code=204)
async def remove_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id, Device.user_id == user.id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "Device not found."}})
    await db.delete(device)
    await db.commit()


@router.post("/devices/pair", status_code=201)
async def initiate_pairing(
    body: PairDeviceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PairDeviceResponse:
    # TODO: relay device_pair_prompt via gateway
    pair_id = "pair_" + secrets.token_urlsafe(16)
    return PairDeviceResponse(pair_id=pair_id)


@router.post("/devices/pair/{pair_id}/respond", status_code=204)
async def respond_to_pairing(
    pair_id: str,
    body: PairRespondRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # TODO: relay approval/denial via gateway
    pass


@router.put("/backup", status_code=204)
async def upload_key_backup(
    body: KeyBackupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(KeyBackup).where(KeyBackup.user_id == user.id))
    existing = result.scalar_one_or_none()
    if existing:
        existing.encrypted_blob = body.encrypted_blob
    else:
        db.add(KeyBackup(user_id=user.id, encrypted_blob=body.encrypted_blob))
    await db.commit()


@router.get("/backup")
async def download_key_backup(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KeyBackupResponse:
    result = await db.execute(select(KeyBackup).where(KeyBackup.user_id == user.id))
    backup = result.scalar_one_or_none()
    if backup is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "KEY_BACKUP_NOT_FOUND", "message": "No recovery backup exists."}})
    return KeyBackupResponse(encrypted_blob=backup.encrypted_blob)


@router.post("/reset", status_code=204)
async def reset_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Delete all prekeys and one-time prekeys for user's devices
    devices = (await db.execute(select(Device).where(Device.user_id == user.id))).scalars().all()
    for dev in devices:
        await db.execute(select(Prekey).where(Prekey.device_id == dev.id))
        # Delete prekeys
        from sqlalchemy import delete
        await db.execute(delete(Prekey).where(Prekey.device_id == dev.id))
        await db.execute(delete(OneTimePrekey).where(OneTimePrekey.device_id == dev.id))
    await db.commit()
    # TODO: broadcast key_reset_notify via gateway

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from vox.api.deps import get_current_user, get_db
from vox.db.models import Device, KeyBackup, OneTimePrekey, Prekey, User, dm_participants
from vox.limits import limits
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
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
    # Enforce device limit
    count = await db.scalar(
        select(func.count()).select_from(Device).where(Device.user_id == user.id)
    )
    if count is not None and count >= limits.max_devices:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "DEVICE_LIMIT_REACHED", "message": f"Maximum of {limits.max_devices} devices allowed."}},
        )
    db.add(Device(id=body.device_id, user_id=user.id, device_name=body.device_name, created_at=datetime.now(timezone.utc)))
    await db.commit()
    devices_result = await db.execute(select(Device).where(Device.user_id == user.id))
    device_list = [{"device_id": d.id, "device_name": d.device_name} for d in devices_result.scalars().all()]
    await dispatch(gw.device_list_update(device_list), user_ids=[user.id])
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
    devices_result = await db.execute(select(Device).where(Device.user_id == user.id))
    device_list = [{"device_id": d.id, "device_name": d.device_name} for d in devices_result.scalars().all()]
    await dispatch(gw.device_list_update(device_list), user_ids=[user.id])


@router.post("/devices/pair", status_code=201)
async def initiate_pairing(
    body: PairDeviceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PairDeviceResponse:
    pair_id = "pair_" + secrets.token_urlsafe(16)
    await dispatch(
        gw.device_pair_prompt(
            device_name=body.device_name,
            ip=request.client.host if request.client else "unknown",
            location="",
            pair_id=pair_id,
        ),
        user_ids=[user.id],
    )
    return PairDeviceResponse(pair_id=pair_id)


@router.post("/devices/pair/{pair_id}/respond", status_code=204)
async def respond_to_pairing(
    pair_id: str,
    body: PairRespondRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await dispatch(
        gw.cpace_confirm(pair_id=pair_id, data="approved" if body.approved else "denied"),
        user_ids=[user.id],
    )


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
        from sqlalchemy import delete
        await db.execute(delete(Prekey).where(Prekey.device_id == dev.id))
        await db.execute(delete(OneTimePrekey).where(OneTimePrekey.device_id == dev.id))
    await db.commit()
    result = await db.execute(
        select(dm_participants.c.user_id)
        .where(
            dm_participants.c.dm_id.in_(
                select(dm_participants.c.dm_id).where(dm_participants.c.user_id == user.id)
            )
        )
        .where(dm_participants.c.user_id != user.id)
    )
    contact_ids = list(result.scalars().all())
    if contact_ids:
        await dispatch(gw.key_reset_notify(user_id=user.id), user_ids=contact_ids)

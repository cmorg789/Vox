"""Federation S2S API endpoints — 9 inbound endpoints for cross-server communication."""

from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_db
from vox.api.messages import _snowflake
from vox.db.models import (
    AuditLog,
    Ban,
    Config,
    DM,
    Device,
    FederationEntry,
    Invite,
    Message,
    OneTimePrekey,
    Prekey,
    Session,
    User,
    dm_participants,
)
from vox.federation.deps import verify_federation_request
from vox.db.models import ConfigKey
from vox.federation.service import (
    _get_config,
    add_presence_sub,
    verify_voucher,
)
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.federation import (
    FederatedDevicePrekey,
    FederatedPrekeyResponse,
    FederatedUserProfile,
    FederationBlockRequest,
    FederationJoinRequest,
    FederationJoinResponse,
    PresenceNotifyRequest,
    PresenceSubscribeRequest,
    RelayMessageRequest,
    RelayReadRequest,
    RelayTypingRequest,
)

router = APIRouter(prefix="/api/v1/federation", tags=["federation"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _find_local_user(db: AsyncSession, user_address: str) -> User | None:
    """Extract username from user@domain and find the local user."""
    if "@" not in user_address:
        return None
    username = user_address.split("@", 1)[0]
    result = await db.execute(select(User).where(User.username == username, User.federated == False))
    return result.scalar_one_or_none()


async def _find_or_create_federated_user(
    db: AsyncSession, user_address: str
) -> User:
    """Find or create a stub User for a federated remote user."""
    if "@" not in user_address:
        raise ValueError("Invalid user address")
    username_part, domain = user_address.split("@", 1)
    # Use the full address as the username for federated stubs
    fed_username = user_address
    result = await db.execute(
        select(User).where(User.username == fed_username, User.federated == True)
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        username=fed_username,
        display_name=username_part,
        federated=True,
        home_domain=domain,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _find_or_create_dm(db: AsyncSession, user_a_id: int, user_b_id: int) -> DM:
    """Find existing 1:1 DM between two users, or create one."""
    existing = await db.execute(
        select(dm_participants.c.dm_id)
        .where(dm_participants.c.user_id == user_a_id)
        .intersect(
            select(dm_participants.c.dm_id).where(dm_participants.c.user_id == user_b_id)
        )
    )
    existing_dm_id = existing.scalar_one_or_none()
    if existing_dm_id is not None:
        result = await db.execute(select(DM).where(DM.id == existing_dm_id))
        dm = result.scalar_one_or_none()
        if dm and not dm.is_group:
            return dm

    dm = DM(is_group=False, created_at=datetime.now(timezone.utc))
    db.add(dm)
    await db.flush()
    await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=user_a_id))
    await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=user_b_id))
    return dm


async def _get_dm_participant_ids(db: AsyncSession, dm_id: int) -> list[int]:
    result = await db.execute(select(dm_participants.c.user_id).where(dm_participants.c.dm_id == dm_id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Relay Endpoints
# ---------------------------------------------------------------------------


@router.post("/relay/message", status_code=204)
async def relay_message(
    body: RelayMessageRequest,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
):
    # Validate origin matches sender domain
    if "@" in body.from_:
        sender_domain = body.from_.split("@", 1)[1]
        if sender_domain != origin:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "FED_AUTH_FAILED", "message": "Origin does not match sender domain."}},
            )

    recipient = await _find_local_user(db, body.to)
    if recipient is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FED_USER_NOT_FOUND", "message": "Recipient not found on this server."}},
        )

    sender = await _find_or_create_federated_user(db, body.from_)
    dm = await _find_or_create_dm(db, sender.id, recipient.id)

    msg_id = await _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(
        id=msg_id,
        dm_id=dm.id,
        author_id=sender.id,
        opaque_blob=body.opaque_blob,
        timestamp=ts,
        federated=True,
        author_address=body.from_,
    )
    db.add(msg)
    await db.commit()

    pids = await _get_dm_participant_ids(db, dm.id)
    await dispatch(
        gw.message_create(msg_id=msg_id, dm_id=dm.id, author_id=sender.id, body=None, timestamp=ts),
        user_ids=pids,
    )


@router.post("/relay/typing", status_code=204)
async def relay_typing(
    body: RelayTypingRequest,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
):
    recipient = await _find_local_user(db, body.to)
    if recipient is None:
        return  # Silently ignore

    sender = await _find_or_create_federated_user(db, body.from_)

    # Find existing DM
    existing = await db.execute(
        select(dm_participants.c.dm_id)
        .where(dm_participants.c.user_id == sender.id)
        .intersect(
            select(dm_participants.c.dm_id).where(dm_participants.c.user_id == recipient.id)
        )
    )
    dm_id = existing.scalar_one_or_none()
    if dm_id is None:
        return  # Silently ignore

    pids = await _get_dm_participant_ids(db, dm_id)
    await dispatch(gw.typing_start(user_id=sender.id, dm_id=dm_id), user_ids=pids)


@router.post("/relay/read", status_code=204)
async def relay_read(
    body: RelayReadRequest,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
):
    recipient = await _find_local_user(db, body.to)
    if recipient is None:
        return

    sender = await _find_or_create_federated_user(db, body.from_)

    existing = await db.execute(
        select(dm_participants.c.dm_id)
        .where(dm_participants.c.user_id == sender.id)
        .intersect(
            select(dm_participants.c.dm_id).where(dm_participants.c.user_id == recipient.id)
        )
    )
    dm_id = existing.scalar_one_or_none()
    if dm_id is None:
        return

    pids = await _get_dm_participant_ids(db, dm_id)
    await dispatch(
        gw.dm_read_notify(dm_id=dm_id, user_id=sender.id, up_to_msg_id=body.up_to_msg_id),
        user_ids=pids,
    )


# ---------------------------------------------------------------------------
# User Info Endpoints
# ---------------------------------------------------------------------------


@router.get("/users/{user_address}/prekeys")
async def get_federated_prekeys(
    user_address: str,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
) -> FederatedPrekeyResponse:
    user = await _find_local_user(db, user_address)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FED_USER_NOT_FOUND", "message": "User not found on this server."}},
        )

    devices_result = await db.execute(select(Device).where(Device.user_id == user.id))
    devices = devices_result.scalars().all()

    bundles = []
    for dev in devices:
        prekey_result = await db.execute(select(Prekey).where(Prekey.device_id == dev.id))
        prekey = prekey_result.scalar_one_or_none()
        if prekey is None:
            continue

        otp_result = await db.execute(
            select(OneTimePrekey).where(OneTimePrekey.device_id == dev.id).limit(1)
        )
        otp = otp_result.scalar_one_or_none()
        otp_key = None
        if otp:
            otp_key = otp.key_data
            await db.delete(otp)

        bundles.append(FederatedDevicePrekey(
            device_id=dev.id,
            identity_key=prekey.identity_key,
            signed_prekey=prekey.signed_prekey,
            one_time_prekey=otp_key,
        ))

    await db.commit()
    return FederatedPrekeyResponse(user_address=user_address, devices=bundles)


@router.get("/users/{user_address}")
async def get_federated_profile(
    user_address: str,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
) -> FederatedUserProfile:
    user = await _find_local_user(db, user_address)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FED_USER_NOT_FOUND", "message": "User not found on this server."}},
        )
    return FederatedUserProfile(
        display_name=user.display_name or user.username,
        avatar_url=user.avatar,
        bio=user.bio,
    )


# ---------------------------------------------------------------------------
# Presence Endpoints
# ---------------------------------------------------------------------------


@router.post("/presence/subscribe", status_code=204)
async def presence_subscribe(
    body: PresenceSubscribeRequest,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
):
    user = await _find_local_user(db, body.user_address)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FED_USER_NOT_FOUND", "message": "User not found on this server."}},
        )
    add_presence_sub(origin, body.user_address)


@router.post("/presence/notify", status_code=204)
async def presence_notify(
    body: PresenceNotifyRequest,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
):
    # Find the federated user stub
    fed_user_result = await db.execute(
        select(User).where(User.username == body.user_address, User.federated == True)
    )
    fed_user = fed_user_result.scalar_one_or_none()
    if fed_user is None:
        return  # Silently ignore

    # Find local users in DMs with this federated user
    dm_ids_result = await db.execute(
        select(dm_participants.c.dm_id).where(dm_participants.c.user_id == fed_user.id)
    )
    dm_ids = list(dm_ids_result.scalars().all())

    local_user_ids: set[int] = set()
    for dm_id in dm_ids:
        pids = await _get_dm_participant_ids(db, dm_id)
        for pid in pids:
            if pid != fed_user.id:
                local_user_ids.add(pid)

    if local_user_ids:
        await dispatch(
            gw.presence_update(user_id=fed_user.id, status=body.status),
            user_ids=list(local_user_ids),
        )


# ---------------------------------------------------------------------------
# Join & Block
# ---------------------------------------------------------------------------


@router.post("/join")
async def federation_join(
    body: FederationJoinRequest,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
) -> FederationJoinResponse:
    # Verify voucher
    our_domain = await _get_config(db, ConfigKey.FEDERATION_DOMAIN)
    if our_domain is None:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "FED_NOT_CONFIGURED", "message": "Federation domain not configured."}},
        )

    voucher_data = await verify_voucher(body.voucher, our_domain, db=db)
    if voucher_data is None:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FED_AUTH_FAILED", "message": "Invalid or expired voucher."}},
        )

    if voucher_data.get("user_address") != body.user_address:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FED_AUTH_FAILED", "message": "Voucher user_address mismatch."}},
        )

    # Optionally validate invite code
    if body.invite_code:
        result = await db.execute(select(Invite).where(Invite.code == body.invite_code))
        invite = result.scalar_one_or_none()
        if invite is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "INVITE_NOT_FOUND", "message": "Invite code not found."}},
            )
        if invite.max_uses and invite.uses >= invite.max_uses:
            raise HTTPException(
                status_code=410,
                detail={"error": {"code": "INVITE_EXPIRED", "message": "Invite has been used up."}},
            )
        if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=410,
                detail={"error": {"code": "INVITE_EXPIRED", "message": "Invite has expired."}},
            )
        invite.uses += 1

    # Check bans
    fed_user = await _find_or_create_federated_user(db, body.user_address)
    ban_result = await db.execute(select(Ban).where(Ban.user_id == fed_user.id))
    if ban_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "BANNED", "message": "User is banned from this server."}},
        )

    # Create federation token
    fed_token = "fed_" + secrets.token_urlsafe(48)
    session = Session(
        token=fed_token,
        user_id=fed_user.id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(session)
    await db.commit()

    # Build server info
    server_name = await _get_config(db, ConfigKey.SERVER_NAME) or "Vox Server"
    server_info = {"name": server_name, "domain": our_domain}

    return FederationJoinResponse(
        accepted=True,
        federation_token=fed_token,
        server_info=server_info,
    )


@router.post("/block", status_code=204)
async def federation_block(
    body: FederationBlockRequest,
    origin: str = Depends(verify_federation_request),
    db: AsyncSession = Depends(get_db),
):
    # Add origin to blocklist (idempotent — skip if already blocked)
    existing = await db.execute(
        select(FederationEntry).where(FederationEntry.entry == origin)
    )
    if existing.scalar_one_or_none() is None:
        db.add(FederationEntry(
            entry=origin,
            reason=body.reason or "Remote server initiated block",
            created_at=datetime.now(timezone.utc),
        ))

    # Deactivate all federated users from that domain
    fed_users = await db.execute(
        select(User).where(User.home_domain == origin, User.federated == True)
    )
    for u in fed_users.scalars().all():
        u.active = False

    # Audit log
    db.add(AuditLog(
        id=await _snowflake(),
        event_type="federation_block_received",
        actor_id=0,
        extra=json.dumps({"origin": origin, "reason": body.reason}),
        timestamp=int(time.time() * 1000),
    ))
    await db.commit()

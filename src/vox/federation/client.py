"""Outbound federation client — thin wrappers around send_federation_request."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from vox.federation.service import (
    create_voucher,
    get_private_key,
    get_our_domain,
    send_federation_request,
)


async def relay_dm_message(
    db: AsyncSession, from_addr: str, to_addr: str, opaque_blob: str
) -> bool:
    domain = to_addr.split("@", 1)[1] if "@" in to_addr else None
    if domain is None:
        return False
    resp = await send_federation_request(
        db, domain, "/api/v1/federation/relay/message",
        {"from": from_addr, "to": to_addr, "opaque_blob": opaque_blob},
    )
    return resp is not None and resp.status_code < 300


async def relay_typing(db: AsyncSession, from_addr: str, to_addr: str) -> bool:
    domain = to_addr.split("@", 1)[1] if "@" in to_addr else None
    if domain is None:
        return False
    resp = await send_federation_request(
        db, domain, "/api/v1/federation/relay/typing",
        {"from": from_addr, "to": to_addr},
    )
    return resp is not None and resp.status_code < 300


async def relay_read_receipt(
    db: AsyncSession, from_addr: str, to_addr: str, up_to_msg_id: int
) -> bool:
    domain = to_addr.split("@", 1)[1] if "@" in to_addr else None
    if domain is None:
        return False
    resp = await send_federation_request(
        db, domain, "/api/v1/federation/relay/read",
        {"from": from_addr, "to": to_addr, "up_to_msg_id": up_to_msg_id},
    )
    return resp is not None and resp.status_code < 300


async def fetch_remote_prekeys(db: AsyncSession, user_address: str) -> dict | None:
    domain = user_address.split("@", 1)[1] if "@" in user_address else None
    if domain is None:
        return None
    resp = await send_federation_request(
        db, domain, f"/api/v1/federation/users/{user_address}/prekeys",
        method="GET",
    )
    if resp is not None and resp.status_code == 200:
        return resp.json()
    return None


async def fetch_remote_profile(db: AsyncSession, user_address: str) -> dict | None:
    domain = user_address.split("@", 1)[1] if "@" in user_address else None
    if domain is None:
        return None
    resp = await send_federation_request(
        db, domain, f"/api/v1/federation/users/{user_address}",
        method="GET",
    )
    if resp is not None and resp.status_code == 200:
        return resp.json()
    return None


async def subscribe_presence(db: AsyncSession, user_address: str) -> bool:
    domain = user_address.split("@", 1)[1] if "@" in user_address else None
    if domain is None:
        return False
    resp = await send_federation_request(
        db, domain, "/api/v1/federation/presence/subscribe",
        {"user_address": user_address},
    )
    return resp is not None and resp.status_code < 300


async def notify_presence(
    db: AsyncSession, domain: str, user_address: str, status: str, activity: str | None = None
) -> bool:
    body: dict = {"user_address": user_address, "status": status}
    if activity:
        body["activity"] = activity
    resp = await send_federation_request(
        db, domain, "/api/v1/federation/presence/notify", body,
    )
    return resp is not None and resp.status_code < 300


async def send_join_request(
    db: AsyncSession, user_address: str, target_domain: str, invite_code: str | None = None
) -> dict | None:
    private_key = await get_private_key(db)
    voucher = create_voucher(user_address, target_domain, private_key)
    body: dict = {"user_address": user_address, "voucher": voucher}
    if invite_code:
        body["invite_code"] = invite_code
    resp = await send_federation_request(
        db, target_domain, "/api/v1/federation/join", body,
    )
    if resp is not None and resp.status_code == 200:
        return resp.json()
    return None


async def send_block_notification(db: AsyncSession, domain: str, reason: str | None = None) -> bool:
    body: dict = {}
    if reason:
        body["reason"] = reason
    resp = await send_federation_request(
        db, domain, "/api/v1/federation/block", body,
    )
    return resp is not None and resp.status_code < 300

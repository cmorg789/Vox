"""Core federation service: crypto, DNS, HTTP client, policy, and vouchers."""

from __future__ import annotations

import base64
import json
import secrets
import time

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.db.models import FederationEntry, FederationNonce

# ---------------------------------------------------------------------------
# Key Management
# ---------------------------------------------------------------------------


async def get_or_create_keypair(
    db: AsyncSession,
) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    from vox.config import config, save_config_value

    priv_b64 = config.federation.private_key
    pub_b64 = config.federation.public_key

    if priv_b64 and pub_b64:
        priv_bytes = base64.b64decode(priv_b64)
        private_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
        return private_key, private_key.public_key()

    private_key = Ed25519PrivateKey.generate()
    priv_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    await save_config_value(db, "federation_private_key", base64.b64encode(priv_bytes).decode())
    await save_config_value(db, "federation_public_key", base64.b64encode(pub_bytes).decode())
    await db.commit()

    return private_key, private_key.public_key()


async def get_private_key(db: AsyncSession) -> Ed25519PrivateKey:
    private_key, _ = await get_or_create_keypair(db)
    return private_key


async def get_public_key_b64(db: AsyncSession) -> str:
    _, public_key = await get_or_create_keypair(db)
    pub_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(pub_bytes).decode()


# ---------------------------------------------------------------------------
# Signing & Verification
# ---------------------------------------------------------------------------


def sign_body(body: bytes, private_key: Ed25519PrivateKey) -> str:
    sig = private_key.sign(body)
    return base64.b64encode(sig).decode()


def verify_signature(body: bytes, sig_b64: str, pub_key_b64: str) -> bool:
    try:
        sig = base64.b64decode(sig_b64)
        pub_bytes = base64.b64decode(pub_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        public_key.verify(sig, body)
        return True
    except Exception:
        return False


async def verify_signature_for_origin(body: bytes, sig_b64: str, origin: str) -> bool:
    pub_b64 = await lookup_vox_key(origin)
    if pub_b64 is None:
        return False
    return verify_signature(body, sig_b64, pub_b64)


# ---------------------------------------------------------------------------
# DNS Lookups
# ---------------------------------------------------------------------------


async def lookup_vox_key(domain: str) -> str | None:
    try:
        import dns.asyncresolver

        answers = await dns.asyncresolver.resolve(f"_voxkey.{domain}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            for part in txt.split(";"):
                part = part.strip()
                if part.startswith("p="):
                    return part[2:]
    except Exception:
        pass
    return None


async def lookup_vox_policy(domain: str) -> dict:
    try:
        import dns.asyncresolver

        answers = await dns.asyncresolver.resolve(f"_voxpolicy.{domain}", "TXT")
        result: dict = {}
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            for part in txt.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    result[k.strip()] = v.strip()
        return result if result else {"federation": "open"}
    except Exception:
        return {"federation": "open"}


async def lookup_vox_host(domain: str) -> tuple[str, int]:
    try:
        import dns.asyncresolver

        answers = await dns.asyncresolver.resolve(f"_vox.{domain}", "SVCB")
        for rdata in answers:
            target = str(rdata.target).rstrip(".")
            port = rdata.params.get(3)  # port key in SVCB
            return target, int(port) if port else 443
    except Exception:
        pass
    return (domain, 443)


# ---------------------------------------------------------------------------
# Policy & Blocklist
# ---------------------------------------------------------------------------


async def check_federation_allowed(
    db: AsyncSession, domain: str, direction: str = "inbound"
) -> bool:
    # Check blocklist
    result = await db.execute(
        select(FederationEntry).where(FederationEntry.entry == domain)
    )
    if result.scalar_one_or_none() is not None:
        return False

    if direction == "inbound":
        from vox.config import config
        policy = config.federation.policy
        if policy == "closed":
            return False
        if policy == "allowlist":
            # Check if domain is in allow list (stored as federation entry with reason "allow")
            result = await db.execute(
                select(FederationEntry).where(
                    FederationEntry.entry == f"allow:{domain}"
                )
            )
            return result.scalar_one_or_none() is not None
        # Default: open
        return True
    else:
        # Outbound: best-effort check remote policy
        remote_policy = await lookup_vox_policy(domain)
        return remote_policy.get("federation", "open") != "closed"


async def get_our_domain(db: AsyncSession) -> str | None:
    from vox.config import config
    return config.federation.domain


# ---------------------------------------------------------------------------
# Voucher System
# ---------------------------------------------------------------------------

def create_voucher(
    user_address: str,
    target_domain: str,
    private_key: Ed25519PrivateKey,
    ttl: int = 300,
) -> str:
    now = time.time()
    payload = {
        "user_address": user_address,
        "target_domain": target_domain,
        "issued_at": now,
        "expires_at": now + ttl,
        "nonce": secrets.token_urlsafe(16),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    sig = sign_body(payload_bytes, private_key)
    payload_b64 = base64.b64encode(payload_bytes).decode()
    return f"{payload_b64}.{sig}"


async def verify_voucher(voucher: str, expected_target: str, db: AsyncSession | None = None) -> dict | None:
    try:
        parts = voucher.split(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        payload_bytes = base64.b64decode(payload_b64)
        payload = json.loads(payload_bytes)

        # Check target domain
        if payload.get("target_domain") != expected_target:
            return None

        # Check expiry
        now = time.time()
        if now > payload.get("expires_at", 0):
            return None

        # Verify signature using origin's public key
        nonce = payload.get("nonce", "")
        user_address = payload.get("user_address", "")
        if "@" not in user_address:
            return None
        home_domain = user_address.split("@", 1)[1]
        pub_b64 = await lookup_vox_key(home_domain)
        if pub_b64 is None:
            return None
        if not verify_signature(payload_bytes, sig_b64, pub_b64):
            return None

        # Mark nonce as seen in DB (atomic via unique constraint on PK).
        # If a concurrent request already inserted this nonce, the flush
        # raises IntegrityError and we reject the duplicate.
        if db is not None:
            from datetime import datetime, timedelta, timezone
            from sqlalchemy.exc import IntegrityError
            nonce_row = FederationNonce(
                nonce=nonce,
                seen_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            db.add(nonce_row)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                return None

        return payload

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Presence Subscriptions (DB-backed)
# ---------------------------------------------------------------------------


async def add_presence_sub(db: AsyncSession, domain: str, address: str) -> None:
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from vox.db.models import FederationPresenceSub
    stmt = sqlite_insert(FederationPresenceSub).values(domain=domain, user_address=address).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.flush()


async def get_presence_subscribers(db: AsyncSession, address: str) -> list[str]:
    """Return list of domains subscribed to this user's presence."""
    from vox.db.models import FederationPresenceSub
    result = await db.execute(
        select(FederationPresenceSub.domain).where(FederationPresenceSub.user_address == address)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Outbound HTTP Client
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def close_http_client() -> None:
    """Close the federation HTTP client to prevent resource leaks."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def send_federation_request(
    db: AsyncSession,
    target_domain: str,
    path: str,
    body: dict | None = None,
    method: str = "POST",
) -> httpx.Response | None:
    try:
        host, port = await lookup_vox_host(target_domain)
        private_key = await get_private_key(db)
        our_domain = await get_our_domain(db)
        if our_domain is None:
            return None

        body_bytes = json.dumps(body or {}, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        sig = sign_body(body_bytes + timestamp.encode(), private_key)

        scheme = "https"
        url = f"{scheme}://{host}:{port}{path}"
        headers = {
            "X-Vox-Origin": our_domain,
            "X-Vox-Signature": sig,
            "X-Vox-Timestamp": timestamp,
            "Content-Type": "application/json",
        }

        client = _get_http_client()
        response = await client.request(method, url, content=body_bytes, headers=headers)
        return response
    except Exception:
        return None

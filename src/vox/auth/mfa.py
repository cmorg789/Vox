import json
import secrets
import string
from datetime import datetime, timedelta, timezone

import pyotp
import webauthn
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from vox.db.models import RecoveryCode, Session, WebAuthnChallenge, WebAuthnCredential

_ph = PasswordHasher()

_CHALLENGE_TTL_MINUTES = 5


# --- TOTP ---


def generate_totp_secret(username: str, issuer: str = "Vox") -> tuple[str, str]:
    """Generate a TOTP secret and provisioning URI."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name=issuer)
    return secret, uri


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code with a 1-step window."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# --- Recovery Codes ---


def generate_recovery_codes(count: int = 8) -> list[str]:
    """Generate recovery codes in XXXX-XXXX format (uppercase alphanumeric)."""
    alphabet = string.ascii_uppercase + string.digits
    codes = []
    for _ in range(count):
        part1 = "".join(secrets.choice(alphabet) for _ in range(4))
        part2 = "".join(secrets.choice(alphabet) for _ in range(4))
        codes.append(f"{part1}-{part2}")
    return codes


async def store_recovery_codes(
    db: AsyncSession, user_id: int, codes: list[str]
) -> None:
    """Delete old recovery codes and store new hashed ones."""
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
    for code in codes:
        rc = RecoveryCode(
            user_id=user_id,
            code_hash=_ph.hash(code),
            used=False,
        )
        db.add(rc)
    await db.flush()


async def verify_recovery_code(
    db: AsyncSession, user_id: int, code: str
) -> bool:
    """Try each unused recovery code hash; mark used on match."""
    result = await db.execute(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user_id, RecoveryCode.used == False
        )
    )
    for rc in result.scalars().all():
        try:
            _ph.verify(rc.code_hash, code)
            rc.used = True
            await db.flush()
            return True
        except VerifyMismatchError:
            continue
    return False


# --- Setup / MFA Sessions ---


async def create_setup_session(
    db: AsyncSession, user_id: int, prefix: str
) -> str:
    """Create a short-lived session token for 2FA setup."""
    from vox.auth.service import generate_token

    token = prefix + generate_token()
    session = Session(
        token=token,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(session)
    await db.flush()
    return token


async def validate_setup_session(
    db: AsyncSession, token: str, prefix: str
) -> Session:
    """Validate a setup session token. Raises 401 if expired/invalid."""
    if not token.startswith(prefix):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "2FA_SETUP_EXPIRED", "message": "Setup session is invalid."}},
        )
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Session).where(Session.token == token, Session.expires_at > now)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "2FA_SETUP_EXPIRED", "message": "Setup session expired."}},
        )
    return session


async def validate_mfa_ticket(db: AsyncSession, ticket: str) -> Session:
    """Validate an MFA ticket session. Raises 401 if invalid."""
    if not ticket.startswith("mfa_"):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "2FA_INVALID_CODE", "message": "Invalid MFA ticket."}},
        )
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Session).where(Session.token == ticket, Session.expires_at > now)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "2FA_INVALID_CODE", "message": "MFA ticket expired or invalid."}},
        )
    return session


# --- WebAuthn RP Config ---


def _get_webauthn_config() -> tuple[str, str]:
    """Get WebAuthn RP ID and origin from in-memory config."""
    from vox.config import config
    return config.webauthn.rp_id, config.webauthn.origin


# --- WebAuthn Challenge DB helpers ---


async def _store_challenge(
    db: AsyncSession,
    challenge_id: str,
    user_id: int,
    challenge_type: str,
    challenge_data: dict,
) -> None:
    """Store a WebAuthn challenge in the database."""
    row = WebAuthnChallenge(
        id=challenge_id,
        user_id=user_id,
        challenge_type=challenge_type,
        challenge_data=json.dumps(challenge_data),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=_CHALLENGE_TTL_MINUTES),
    )
    db.add(row)
    await db.flush()


async def _pop_challenge(
    db: AsyncSession,
    challenge_id: str,
    expected_type: str,
) -> dict | None:
    """Retrieve and delete a WebAuthn challenge from the database. Returns None if expired/missing."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(WebAuthnChallenge).where(
            WebAuthnChallenge.id == challenge_id,
            WebAuthnChallenge.challenge_type == expected_type,
            WebAuthnChallenge.expires_at > now,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    data = json.loads(row.challenge_data)
    await db.delete(row)
    await db.flush()
    return data


# --- WebAuthn Registration ---


async def generate_webauthn_registration(
    db: AsyncSession,
    user_id: int,
    username: str,
) -> tuple[str, dict]:
    """Generate WebAuthn registration options and store challenge."""
    rp_id, origin = _get_webauthn_config()

    # Exclude existing credentials
    existing = await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    )
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in existing.scalars().all()
    ]

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name="Vox",
        user_name=username,
        user_id=user_id.to_bytes(8, "big"),
        exclude_credentials=exclude,
    )

    challenge_id = secrets.token_urlsafe(16)
    options_json = json.loads(webauthn.options_to_json(options))

    await _store_challenge(db, challenge_id, user_id, "registration", {
        "challenge": bytes_to_base64url(options.challenge),
        "rp_id": rp_id,
        "origin": origin,
        "user_id": user_id,
    })

    return challenge_id, options_json


async def verify_webauthn_registration(
    db: AsyncSession,
    challenge_id: str,
    attestation: dict,
) -> tuple[str, str]:
    """Verify WebAuthn registration response. Returns (credential_id, public_key)."""
    challenge_data = await _pop_challenge(db, challenge_id, "registration")
    if challenge_data is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "WEBAUTHN_FAILED", "message": "Invalid or expired challenge."}},
        )

    try:
        verification = webauthn.verify_registration_response(
            credential=attestation,
            expected_challenge=base64url_to_bytes(challenge_data["challenge"]),
            expected_rp_id=challenge_data["rp_id"],
            expected_origin=challenge_data["origin"],
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "WEBAUTHN_FAILED", "message": "WebAuthn verification failed."}},
        )

    credential_id = bytes_to_base64url(verification.credential_id)
    public_key = bytes_to_base64url(verification.credential_public_key)
    return credential_id, public_key


# --- WebAuthn Authentication ---


async def generate_webauthn_authentication(
    db: AsyncSession,
    user_id: int,
) -> tuple[str, dict]:
    """Generate WebAuthn authentication options for a user."""
    rp_id, origin = _get_webauthn_config()

    existing = await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    )
    credentials = existing.scalars().all()
    if not credentials:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "WEBAUTHN_CREDENTIAL_NOT_FOUND", "message": "No WebAuthn credentials found."}},
        )

    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in credentials
    ]

    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow,
    )

    challenge_id = secrets.token_urlsafe(16)
    options_json = json.loads(webauthn.options_to_json(options))

    await _store_challenge(db, challenge_id, user_id, "authentication", {
        "challenge": bytes_to_base64url(options.challenge),
        "rp_id": rp_id,
        "origin": origin,
        "user_id": user_id,
    })

    return challenge_id, options_json


async def verify_webauthn_authentication(
    db: AsyncSession,
    challenge_id: str,
    assertion: dict,
) -> int:
    """Verify WebAuthn authentication response. Returns user_id."""
    challenge_data = await _pop_challenge(db, challenge_id, "authentication")
    if challenge_data is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "WEBAUTHN_FAILED", "message": "Invalid or expired challenge."}},
        )

    # Find the credential being used
    credential_id_b64 = assertion.get("id", "")
    result = await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == credential_id_b64,
            WebAuthnCredential.user_id == challenge_data["user_id"],
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "WEBAUTHN_FAILED", "message": "Credential not found."}},
        )

    try:
        verification = webauthn.verify_authentication_response(
            credential=assertion,
            expected_challenge=base64url_to_bytes(challenge_data["challenge"]),
            expected_rp_id=challenge_data["rp_id"],
            expected_origin=challenge_data["origin"],
            credential_public_key=base64url_to_bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "WEBAUTHN_FAILED", "message": "WebAuthn authentication failed."}},
        )

    # Update sign count and last_used_at
    cred.sign_count = verification.new_sign_count
    cred.last_used_at = datetime.now(timezone.utc)
    await db.flush()

    return challenge_data["user_id"]

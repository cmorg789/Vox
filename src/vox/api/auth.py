from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Header, Response
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType

from vox.api.deps import get_current_user, get_db
from vox.auth.mfa import (
    create_setup_session,
    generate_recovery_codes,
    generate_totp_secret,
    generate_webauthn_authentication,
    generate_webauthn_registration,
    store_recovery_codes,
    validate_mfa_ticket,
    validate_setup_session,
    verify_recovery_code,
    verify_totp,
    verify_webauthn_authentication,
    verify_webauthn_registration,
)
from vox.auth.service import authenticate, create_session, create_user, get_user_role_ids

from vox.db.models import Role, TOTPSecret, User, WebAuthnCredential, RecoveryCode, role_members
from vox.models.auth import (
    FederationTokenLoginRequest,
    Login2FARequest,
    LoginRequest,
    LoginResponse,
    MFARemoveRequest,
    MFARequiredResponse,
    MFASetupConfirmRequest,
    MFASetupConfirmResponse,
    MFASetupRequest,
    MFASetupResponse,
    MFAStatusResponse,
    RegisterRequest,
    RegisterResponse,
    WebAuthnChallengeRequest,
    WebAuthnChallengeResponse,
    WebAuthnCredentialResponse,
    WebAuthnLoginRequest,
)
from vox.permissions import ADMINISTRATOR, EVERYONE_DEFAULTS

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> RegisterResponse:
    # Check if username is taken
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail={"error": {"code": "AUTH_FAILED", "message": "Username already taken."}})

    # Ensure @everyone base role exists (position=0)
    everyone = (await db.execute(select(Role).where(Role.position == 0))).scalar_one_or_none()
    first_user = everyone is None
    if first_user:
        everyone = Role(name="@everyone", position=0, permissions=EVERYONE_DEFAULTS)
        db.add(everyone)
        await db.flush()

    user, token = await create_user(db, body.username, body.password, body.display_name)

    # First registered user is the server owner — grant ADMINISTRATOR
    if first_user:
        admin_role = Role(name="Admin", position=1, permissions=ADMINISTRATOR)
        db.add(admin_role)
        await db.flush()
        await db.execute(role_members.insert().values(role_id=admin_role.id, user_id=user.id))

    await db.commit()

    return RegisterResponse(user_id=user.id, token=token)


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse | MFARequiredResponse:
    user = await authenticate(db, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "AUTH_FAILED", "message": "Invalid username or password."}})

    # Check if user has 2FA enabled
    totp = await db.execute(select(TOTPSecret).where(TOTPSecret.user_id == user.id, TOTPSecret.enabled == True))
    webauthn = await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id))
    has_totp = totp.scalar_one_or_none() is not None
    has_webauthn = webauthn.first() is not None

    if has_totp or has_webauthn:
        # Issue an MFA ticket (short-lived token for the 2FA step)
        from vox.auth.service import generate_token
        mfa_ticket = "mfa_" + generate_token()
        # Store the ticket as a temporary session that requires 2FA completion
        from datetime import datetime, timedelta, timezone
        from vox.db.models import Session
        temp_session = Session(
            token=mfa_ticket,
            user_id=user.id,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db.add(temp_session)
        await db.commit()

        methods = []
        if has_totp:
            methods.append("totp")
        if has_webauthn:
            methods.append("webauthn")
        # Check recovery codes
        recovery = await db.execute(
            select(RecoveryCode).where(RecoveryCode.user_id == user.id, RecoveryCode.used == False)
        )
        if recovery.first() is not None:
            methods.append("recovery")

        return MFARequiredResponse(mfa_ticket=mfa_ticket, available_methods=methods)

    # No 2FA, issue session directly
    token = await create_session(db, user.id)
    role_ids = await get_user_role_ids(db, user.id)
    await db.commit()

    return LoginResponse(
        token=token,
        user_id=user.id,
        display_name=user.display_name,
        roles=role_ids,
    )


@router.get("/2fa")
async def get_2fa_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFAStatusResponse:
    totp = await db.execute(select(TOTPSecret).where(TOTPSecret.user_id == user.id, TOTPSecret.enabled == True))
    webauthn = await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id))
    recovery = await db.execute(
        select(RecoveryCode).where(RecoveryCode.user_id == user.id, RecoveryCode.used == False)
    )

    return MFAStatusResponse(
        totp_enabled=totp.scalar_one_or_none() is not None,
        webauthn_enabled=webauthn.first() is not None,
        recovery_codes_left=len(recovery.all()),
    )


# --- 2FA Login ---


@router.post("/login/2fa")
async def login_2fa(
    body: Login2FARequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    mfa_session = await validate_mfa_ticket(db, body.mfa_ticket)
    user_id = mfa_session.user_id

    if body.method == "totp":
        if not body.code:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "2FA_INVALID_CODE", "message": "TOTP code is required."}},
            )
        result = await db.execute(
            select(TOTPSecret).where(TOTPSecret.user_id == user_id, TOTPSecret.enabled == True)
        )
        totp_secret = result.scalar_one_or_none()
        if totp_secret is None or not verify_totp(totp_secret.secret, body.code):
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "2FA_INVALID_CODE", "message": "Invalid TOTP code."}},
            )

    elif body.method == "webauthn":
        if not body.assertion:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "2FA_INVALID_CODE", "message": "WebAuthn assertion is required."}},
            )
        challenge_id = body.assertion.get("challenge_id", "")
        await verify_webauthn_authentication(db, challenge_id, body.assertion)

    elif body.method == "recovery":
        if not body.code:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "2FA_INVALID_CODE", "message": "Recovery code is required."}},
            )
        if not await verify_recovery_code(db, user_id, body.code):
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "2FA_INVALID_CODE", "message": "Invalid recovery code."}},
            )

    else:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "2FA_INVALID_CODE", "message": "Unsupported 2FA method."}},
        )

    # Delete the MFA session and create a real session
    await db.delete(mfa_session)
    token = await create_session(db, user_id)
    role_ids = await get_user_role_ids(db, user_id)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    await db.commit()

    return LoginResponse(
        token=token,
        user_id=user.id,
        display_name=user.display_name,
        roles=role_ids,
    )


# --- 2FA Setup ---


@router.post("/2fa/setup")
async def setup_2fa(
    body: MFASetupRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    if body.method == "totp":
        # Check if TOTP is already enabled
        result = await db.execute(
            select(TOTPSecret).where(TOTPSecret.user_id == user.id, TOTPSecret.enabled == True)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "2FA_ALREADY_ENABLED", "message": "TOTP is already enabled."}},
            )

        # Delete any pending (not enabled) TOTP secret
        await db.execute(
            delete(TOTPSecret).where(TOTPSecret.user_id == user.id, TOTPSecret.enabled == False)
        )

        secret, uri = generate_totp_secret(user.username)
        totp_row = TOTPSecret(user_id=user.id, secret=secret, enabled=False)
        db.add(totp_row)

        setup_token = await create_setup_session(db, user.id, "setup_totp_")
        await db.commit()

        return MFASetupResponse(
            setup_id=setup_token,
            method="totp",
            totp_secret=secret,
            totp_uri=uri,
        )

    elif body.method == "webauthn":
        challenge_id, options = await generate_webauthn_registration(
            db, user.id, user.username
        )
        setup_token = await create_setup_session(db, user.id, "setup_webauthn_")
        await db.commit()

        return MFASetupResponse(
            setup_id=setup_token,
            method="webauthn",
            creation_options={"challenge_id": challenge_id, **options},
        )

    else:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_METHOD", "message": "Method must be 'totp' or 'webauthn'."}},
        )


@router.post("/2fa/setup/confirm")
async def confirm_2fa_setup(
    body: MFASetupConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupConfirmResponse:
    # Detect method from setup_id prefix
    if body.setup_id.startswith("setup_totp_"):
        setup_session = await validate_setup_session(db, body.setup_id, "setup_totp_")
        if setup_session.user_id != user.id:
            raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Setup session does not belong to this user."}})

        if not body.code:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "2FA_INVALID_CODE", "message": "TOTP code is required."}},
            )

        # Verify the code against the stored (not yet enabled) secret
        result = await db.execute(
            select(TOTPSecret).where(TOTPSecret.user_id == user.id, TOTPSecret.enabled == False)
        )
        totp_secret = result.scalar_one_or_none()
        if totp_secret is None:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "2FA_SETUP_EXPIRED", "message": "No pending TOTP setup found."}},
            )

        if not verify_totp(totp_secret.secret, body.code):
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "2FA_INVALID_CODE", "message": "Invalid TOTP code."}},
            )

        totp_secret.enabled = True

    elif body.setup_id.startswith("setup_webauthn_"):
        setup_session = await validate_setup_session(db, body.setup_id, "setup_webauthn_")
        if setup_session.user_id != user.id:
            raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Setup session does not belong to this user."}})

        if not body.attestation:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "WEBAUTHN_FAILED", "message": "WebAuthn attestation is required."}},
            )

        challenge_id = body.attestation.get("challenge_id", "")
        credential_id, public_key = await verify_webauthn_registration(
            db, challenge_id, body.attestation
        )

        cred = WebAuthnCredential(
            credential_id=credential_id,
            user_id=user.id,
            name=body.credential_name or "Security Key",
            public_key=public_key,
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)

    else:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "2FA_SETUP_EXPIRED", "message": "Invalid setup ID."}},
        )

    # Generate recovery codes only if none exist
    from sqlalchemy import func
    existing = (await db.execute(
        select(func.count()).select_from(RecoveryCode).where(
            RecoveryCode.user_id == user.id, RecoveryCode.used == False
        )
    )).scalar()
    if existing:
        codes = []  # preserve existing codes
    else:
        codes = generate_recovery_codes()
        await store_recovery_codes(db, user.id, codes)

    # Delete the setup session
    await db.delete(setup_session)
    await db.commit()

    return MFASetupConfirmResponse(success=True, recovery_codes=codes)


# --- 2FA Removal ---


@router.delete("/2fa")
async def remove_2fa(
    body: MFARemoveRequest,
    authorization: str = Header(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Verify identity via code (TOTP, WebAuthn assertion, or recovery)
    verified = False
    if body.method == "webauthn" and body.assertion:
        challenge_id = body.assertion.get("challenge_id", "")
        try:
            await verify_webauthn_authentication(db, challenge_id, body.assertion)
            verified = True
        except HTTPException:
            pass
    elif body.code:
        if body.method == "totp":
            result = await db.execute(
                select(TOTPSecret).where(TOTPSecret.user_id == user.id, TOTPSecret.enabled == True)
            )
            totp_secret = result.scalar_one_or_none()
            if totp_secret and verify_totp(totp_secret.secret, body.code):
                verified = True
        if not verified:
            verified = await verify_recovery_code(db, user.id, body.code)
    if not verified:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "2FA_INVALID_CODE", "message": "Invalid verification code."}},
        )

    # Delete the specified method
    if body.method == "totp":
        await db.execute(delete(TOTPSecret).where(TOTPSecret.user_id == user.id))
    elif body.method == "webauthn":
        await db.execute(delete(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id))
    else:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_METHOD", "message": "Method must be 'totp' or 'webauthn'."}},
        )

    # If no 2FA methods remain, also delete recovery codes
    totp_left = await db.execute(
        select(TOTPSecret).where(TOTPSecret.user_id == user.id, TOTPSecret.enabled == True)
    )
    webauthn_left = await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    )
    if totp_left.scalar_one_or_none() is None and webauthn_left.first() is None:
        await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))

    # Invalidate all other sessions for this user (keep current session)
    from vox.db.models import Session as DBSession
    current_token = None
    if authorization.startswith("Bearer "):
        current_token = authorization[7:]
    elif authorization.startswith("Bot "):
        current_token = authorization[4:]
    if current_token:
        await db.execute(
            delete(DBSession).where(
                DBSession.user_id == user.id,
                DBSession.token != current_token,
            )
        )

    await db.commit()
    return {"success": True}


# --- WebAuthn Credentials ---


@router.get("/webauthn/credentials")
async def list_webauthn_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WebAuthnCredentialResponse]:
    result = await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    )
    creds = result.scalars().all()
    return [
        WebAuthnCredentialResponse(
            credential_id=c.credential_id,
            name=c.name,
            registered_at=int(c.registered_at.replace(tzinfo=timezone.utc).timestamp()),
            last_used_at=int(c.last_used_at.replace(tzinfo=timezone.utc).timestamp()) if c.last_used_at else None,
        )
        for c in creds
    ]


@router.delete("/webauthn/credentials/{credential_id}")
async def delete_webauthn_credential(
    credential_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == credential_id,
            WebAuthnCredential.user_id == user.id,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "WEBAUTHN_CREDENTIAL_NOT_FOUND", "message": "Credential not found."}},
        )
    await db.delete(cred)
    await db.commit()
    return {"success": True}


# --- Passwordless WebAuthn Login ---


@router.post("/login/webauthn/challenge")
async def webauthn_login_challenge(
    body: WebAuthnChallengeRequest,
    db: AsyncSession = Depends(get_db),
) -> WebAuthnChallengeResponse:
    result = await db.execute(
        select(User).where(User.username == body.username, User.active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "AUTH_FAILED", "message": "User not found."}},
        )

    challenge_id, options = await generate_webauthn_authentication(db, user.id)
    return WebAuthnChallengeResponse(challenge_id=challenge_id, options=options)


@router.post("/login/webauthn")
async def webauthn_login(
    body: WebAuthnLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    # Look up user by username
    result = await db.execute(
        select(User).where(User.username == body.username, User.active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "AUTH_FAILED", "message": "User not found."}},
        )

    # Build assertion dict from request fields
    assertion = {
        "id": body.credential_id,
        "rawId": body.credential_id,
        "response": {
            "clientDataJSON": body.client_data_json,
            "authenticatorData": body.authenticator_data,
            "signature": body.signature,
        },
        "type": "public-key",
    }
    if body.user_handle:
        assertion["response"]["userHandle"] = body.user_handle

    # Find the most recent pending authentication challenge for this user
    from vox.db.models import WebAuthnChallenge
    now = datetime.now(timezone.utc)
    challenge_result = await db.execute(
        select(WebAuthnChallenge).where(
            WebAuthnChallenge.user_id == user.id,
            WebAuthnChallenge.challenge_type == "authentication",
            WebAuthnChallenge.expires_at > now,
        ).order_by(WebAuthnChallenge.expires_at.desc()).limit(1)
    )
    challenge_row = challenge_result.scalar_one_or_none()
    if challenge_row is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "WEBAUTHN_FAILED", "message": "No pending WebAuthn challenge."}},
        )
    challenge_id = challenge_row.id

    await verify_webauthn_authentication(db, challenge_id, assertion)

    token = await create_session(db, user.id)
    role_ids = await get_user_role_ids(db, user.id)
    await db.commit()

    return LoginResponse(
        token=token,
        user_id=user.id,
        display_name=user.display_name,
        roles=role_ids,
    )


# --- Federation Token Login ---


@router.post("/login/federation")
async def login_federation(
    body: FederationTokenLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    from vox.auth.service import get_user_by_token

    user = await get_user_by_token(db, body.federation_token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "AUTH_FAILED", "message": "Invalid federation token."}},
        )
    if not user.federated:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "AUTH_FAILED", "message": "Token does not belong to a federated user."}},
        )

    # Delete the federation session
    from vox.db.models import Session as DBSession
    result = await db.execute(
        select(DBSession).where(DBSession.token == body.federation_token)
    )
    fed_session = result.scalar_one_or_none()
    if fed_session:
        await db.delete(fed_session)

    # Create a regular session
    token = await create_session(db, user.id)
    role_ids = await get_user_role_ids(db, user.id)
    await db.commit()

    return LoginResponse(
        token=token,
        user_id=user.id,
        display_name=user.display_name,
        roles=role_ids,
    )


# --- Logout ---


@router.post("/logout", status_code=204)
async def logout(
    authorization: str = Header(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Invalidate the current session token."""
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    elif authorization.startswith("Bot "):
        token = authorization[4:]
    else:
        return Response(status_code=204)

    from vox.db.models import Session as DBSession
    await db.execute(delete(DBSession).where(DBSession.token == token, DBSession.user_id == user.id))
    await db.commit()
    return Response(status_code=204)


# --- Session Management ---


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from vox.db.models import Session as DBSession
    result = await db.execute(
        select(DBSession).where(DBSession.user_id == user.id).order_by(DBSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "session_id": s.id,
                "created_at": int(s.created_at.timestamp()),
                "expires_at": int(s.expires_at.timestamp()),
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from vox.db.models import Session as DBSession
    result = await db.execute(select(DBSession).where(DBSession.id == session_id, DBSession.user_id == user.id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SESSION_NOT_FOUND", "message": "Session does not exist."}})
    await db.delete(session)
    await db.commit()

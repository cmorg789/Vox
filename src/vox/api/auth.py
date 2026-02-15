from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.auth.service import authenticate, create_session, create_user, get_user_role_ids
from sqlalchemy import func

from vox.db.models import Role, TOTPSecret, User, WebAuthnCredential, RecoveryCode, role_members
from vox.models.auth import (
    LoginRequest,
    LoginResponse,
    MFARequiredResponse,
    MFAStatusResponse,
    RegisterRequest,
    RegisterResponse,
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

import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vox.db.models import Session, User, role_members

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("__dummy__")

TOKEN_PREFIX = "vox_sess_"
SESSION_LIFETIME_DAYS = 30


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(48)


async def create_user(
    db: AsyncSession,
    username: str,
    password: str,
    display_name: str | None = None,
) -> tuple[User, str]:
    user = User(
        username=username,
        display_name=display_name or username,
        password_hash=hash_password(password),
        federated=False,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    token = generate_token()
    session = Session(
        token=token,
        user_id=user.id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_LIFETIME_DAYS),
    )
    db.add(session)
    await db.flush()

    return user, token


async def authenticate(
    db: AsyncSession, username: str, password: str
) -> User | None:
    result = await db.execute(
        select(User).where(User.username == username, User.active == True)
    )
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None:
        # Perform dummy hash verification to prevent timing attacks
        verify_password(_DUMMY_HASH, password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user


async def create_session(db: AsyncSession, user_id: int) -> str:
    token = generate_token()
    session = Session(
        token=token,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_LIFETIME_DAYS),
    )
    db.add(session)
    await db.flush()
    return token


async def get_user_by_token(db: AsyncSession, token: str) -> User | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.user))
        .where(Session.token == token, Session.expires_at > now)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    return session.user


async def get_user_role_ids(db: AsyncSession, user_id: int) -> list[int]:
    result = await db.execute(
        select(role_members.c.role_id).where(role_members.c.user_id == user_id)
    )
    return list(result.scalars().all())


async def cleanup_expired_sessions(db: AsyncSession) -> None:
    """Delete all expired sessions."""
    from sqlalchemy import delete
    now = datetime.now(timezone.utc)
    await db.execute(delete(Session).where(Session.expires_at <= now))
    await db.commit()

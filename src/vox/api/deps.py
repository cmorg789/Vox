from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.auth.service import get_user_by_token
from vox.db.engine import get_session_factory
from vox.db.models import User
from vox.permissions import has_permission, resolve_permissions


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(),
) -> User:
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    elif authorization.startswith("Bot "):
        token = authorization[4:]
    else:
        raise HTTPException(status_code=401, detail={"error": {"code": "AUTH_FAILED", "message": "Invalid authorization header."}})

    RESTRICTED_PREFIXES = ("mfa_", "setup_totp_", "setup_webauthn_", "fed_")
    if any(token.startswith(p) for p in RESTRICTED_PREFIXES):
        raise HTTPException(status_code=401, detail={"error": {"code": "AUTH_FAILED", "message": "Restricted token cannot be used for authentication."}})

    user = await get_user_by_token(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "AUTH_EXPIRED", "message": "Session token expired or invalid."}})

    if not user.active:
        raise HTTPException(status_code=403, detail={"error": {"code": "BANNED", "message": "Account is deactivated."}})

    return user


def require_permission(
    perm: int,
    *,
    space_type: str | None = None,
    space_id_param: str | None = None,
):
    """FastAPI dependency factory that checks resolved permissions and raises 403."""

    async def checker(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> User:
        space_id = request.path_params.get(space_id_param) if space_id_param else None
        resolved = await resolve_permissions(
            db,
            user.id,
            space_type=space_type,
            space_id=int(space_id) if space_id else None,
        )
        if not has_permission(resolved, perm):
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "MISSING_PERMISSIONS", "message": "You lack the required permissions."}},
            )
        return user

    return Depends(checker)


def resolve_member(*, other_perm: int | None = None):
    """Dependency factory: resolves user_id path param, checks permissions when acting on others.

    Returns (actor, target, is_self).
    If other_perm is None, any authenticated user can act on others (e.g. viewing profiles).
    """

    async def _inner(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        actor: User = Depends(get_current_user),
    ) -> tuple[User, User, bool]:
        try:
            target_id = int(user_id)
        except (ValueError, OverflowError):
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_USER_ID", "message": "user_id must be a numeric ID."}},
            )

        if target_id == actor.id:
            return (actor, actor, True)

        if other_perm is not None:
            resolved = await resolve_permissions(db, actor.id)
            if not has_permission(resolved, other_perm):
                raise HTTPException(
                    status_code=403,
                    detail={"error": {"code": "MISSING_PERMISSIONS", "message": "You lack the required permissions."}},
                )

        result = await db.execute(select(User).where(User.id == target_id))
        target = result.scalar_one_or_none()
        if target is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "USER_NOT_FOUND", "message": "User does not exist."}},
            )
        return (actor, target, False)

    return Depends(_inner)

from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request
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

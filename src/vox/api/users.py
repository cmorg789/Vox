from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.auth.service import get_user_role_ids
from vox.db.models import User, blocks, friends
from vox.limits import limits
from vox.gateway import events
from vox.gateway.dispatch import dispatch
from vox.models.users import (
    FriendResponse,
    UpdateProfileRequest,
    UserResponse,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/{user_id}/presence")
async def get_user_presence(user_id: int, _: User = Depends(get_current_user)):
    from vox.gateway.hub import get_hub
    return get_hub().get_presence(user_id)


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "User does not exist."}})
    role_ids = await get_user_role_ids(db, user.id)
    return UserResponse(user_id=user.id, display_name=user.display_name, avatar=user.avatar, bio=user.bio, roles=role_ids)


@router.patch("/@me")
async def update_profile(
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserResponse:
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.avatar is not None:
        user.avatar = body.avatar
    if body.bio is not None:
        user.bio = body.bio
    await db.commit()
    role_ids = await get_user_role_ids(db, user.id)
    return UserResponse(user_id=user.id, display_name=user.display_name, avatar=user.avatar, bio=user.bio, roles=role_ids)


@router.put("/@me/blocks/{user_id}", status_code=204)
async def block_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_TARGET", "message": "You cannot block yourself."}})
    await db.execute(sqlite_insert(blocks).values(user_id=user.id, blocked_id=user_id).on_conflict_do_nothing())
    await db.commit()
    await dispatch(events.block_add(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id])


@router.delete("/@me/blocks/{user_id}", status_code=204)
async def unblock_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(delete(blocks).where(blocks.c.user_id == user.id, blocks.c.blocked_id == user_id))
    await db.commit()
    await dispatch(events.block_remove(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id])


@router.get("/@me/friends")
async def list_friends(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = min(limit, limits.page_limit_friends)
    query = (
        select(User)
        .join(friends, friends.c.friend_id == User.id)
        .where(friends.c.user_id == user.id)
        .order_by(User.id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(User.id > after)
    result = await db.execute(query)
    friend_list = result.scalars().all()
    items = [
        FriendResponse(user_id=f.id, display_name=f.display_name, avatar=f.avatar)
        for f in friend_list
    ]
    cursor = str(friend_list[-1].id) if friend_list else None
    return {"items": items, "cursor": cursor}


@router.put("/@me/friends/{user_id}", status_code=204)
async def add_friend(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_TARGET", "message": "You cannot add yourself as a friend."}})
    await db.execute(sqlite_insert(friends).values(user_id=user.id, friend_id=user_id).on_conflict_do_nothing())
    await db.commit()
    await dispatch(events.friend_request(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id])


@router.delete("/@me/friends/{user_id}", status_code=204)
async def remove_friend(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(delete(friends).where(friends.c.user_id == user.id, friends.c.friend_id == user_id))
    await db.commit()
    await dispatch(events.friend_remove(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id])

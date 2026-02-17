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


@router.get("/@me")
async def get_current_user_profile(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserResponse:
    role_ids = await get_user_role_ids(db, user.id)
    return UserResponse(user_id=user.id, username=user.username, display_name=user.display_name, avatar=user.avatar, bio=user.bio, roles=role_ids, created_at=int(user.created_at.timestamp()), federated=user.federated, home_domain=user.home_domain)


@router.get("/@me/blocks")
async def list_blocks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(blocks.c.blocked_id).where(blocks.c.user_id == user.id))
    blocked_ids = [row[0] for row in result.all()]
    return {"blocked_user_ids": blocked_ids}


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
    return UserResponse(user_id=user.id, username=user.username, display_name=user.display_name, avatar=user.avatar, bio=user.bio, roles=role_ids, created_at=int(user.created_at.timestamp()), federated=user.federated, home_domain=user.home_domain)


@router.patch("/@me")
async def update_profile(
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserResponse:
    changed = {}
    if body.display_name is not None:
        user.display_name = body.display_name
        changed["display_name"] = body.display_name
    if body.avatar is not None:
        user.avatar = body.avatar
        changed["avatar"] = body.avatar
    if body.bio is not None:
        user.bio = body.bio
        changed["bio"] = body.bio
    await db.commit()
    if changed:
        await dispatch(events.user_update(user_id=user.id, **changed), db=db)
    role_ids = await get_user_role_ids(db, user.id)
    return UserResponse(user_id=user.id, username=user.username, display_name=user.display_name, avatar=user.avatar, bio=user.bio, roles=role_ids, created_at=int(user.created_at.timestamp()), federated=user.federated, home_domain=user.home_domain)


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
    await dispatch(events.block_add(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id], db=db)


@router.delete("/@me/blocks/{user_id}", status_code=204)
async def unblock_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(delete(blocks).where(blocks.c.user_id == user.id, blocks.c.blocked_id == user_id))
    await db.commit()
    await dispatch(events.block_remove(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id], db=db)


@router.get("/@me/friends")
async def list_friends(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = min(limit, limits.page_limit_friends)
    query = (
        select(User, friends.c.status)
        .join(friends, friends.c.friend_id == User.id)
        .where(friends.c.user_id == user.id)
        .order_by(User.id)
        .limit(limit)
    )
    if status is not None:
        query = query.where(friends.c.status == status)
    if after is not None:
        query = query.where(User.id > after)
    result = await db.execute(query)
    rows = result.all()
    items = [
        FriendResponse(user_id=f.id, display_name=f.display_name, avatar=f.avatar, status=s)
        for f, s in rows
    ]
    cursor = str(rows[-1][0].id) if rows else None
    return {"items": items, "cursor": cursor}


@router.put("/@me/friends/{user_id}", status_code=204)
async def add_friend(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_TARGET", "message": "You cannot add yourself as a friend."}})
    from datetime import datetime, timezone
    await db.execute(sqlite_insert(friends).values(user_id=user.id, friend_id=user_id, status="pending", created_at=datetime.now(timezone.utc)).on_conflict_do_nothing())
    await db.commit()
    await dispatch(events.friend_request(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id], db=db)


@router.post("/@me/friends/{user_id}/accept", status_code=204)
async def accept_friend(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Check that user_id sent a pending request to us
    from datetime import datetime, timezone
    row = await db.execute(
        select(friends).where(friends.c.user_id == user_id, friends.c.friend_id == user.id, friends.c.status == "pending")
    )
    if row.first() is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "REQUEST_NOT_FOUND", "message": "No pending friend request from this user."}})
    # Update original request to accepted
    from sqlalchemy import update
    await db.execute(
        update(friends).where(friends.c.user_id == user_id, friends.c.friend_id == user.id).values(status="accepted")
    )
    # Insert reverse row as accepted
    await db.execute(sqlite_insert(friends).values(user_id=user.id, friend_id=user_id, status="accepted", created_at=datetime.now(timezone.utc)).on_conflict_do_nothing())
    await db.commit()
    await dispatch(events.friend_add(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id], db=db)


@router.post("/@me/friends/{user_id}/reject", status_code=204)
async def reject_friend(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Delete the pending request
    result = await db.execute(
        delete(friends).where(friends.c.user_id == user_id, friends.c.friend_id == user.id, friends.c.status == "pending")
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": {"code": "REQUEST_NOT_FOUND", "message": "No pending friend request from this user."}})
    await db.commit()
    await dispatch(events.friend_reject(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id], db=db)


@router.delete("/@me/friends/{user_id}", status_code=204)
async def remove_friend(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Delete both directions
    await db.execute(delete(friends).where(friends.c.user_id == user.id, friends.c.friend_id == user_id))
    await db.execute(delete(friends).where(friends.c.user_id == user_id, friends.c.friend_id == user.id))
    await db.commit()
    await dispatch(events.friend_remove(user_id=user.id, target_id=user_id), user_ids=[user.id, user_id], db=db)

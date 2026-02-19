from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, resolve_member
from vox.auth.service import get_user_role_ids
from vox.db.models import User, blocks, friends
from vox.config import config
from vox.gateway import events
from vox.gateway.dispatch import dispatch
from vox.models.users import (
    BlockListResponse,
    FriendListResponse,
    FriendResponse,
    PresenceResponse,
    UpdateProfileRequest,
    UserResponse,
)
from vox.permissions import ADMINISTRATOR

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/{user_id}/presence")
async def get_user_presence(user_id: int, _: User = Depends(get_current_user)) -> PresenceResponse:
    from vox.gateway.hub import get_hub
    data = get_hub().get_presence(user_id)
    return PresenceResponse(
        user_id=data.get("user_id", user_id),
        status=data.get("status", "offline"),
        custom_status=data.get("custom_status"),
        activity=data.get("activity"),
    )


@router.get("/{user_id}/blocks")
async def list_blocks(
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
) -> BlockListResponse:
    _, target, _ = resolved
    result = await db.execute(select(blocks.c.blocked_id).where(blocks.c.user_id == target.id))
    blocked_ids = [row[0] for row in result.all()]
    return BlockListResponse(blocked_user_ids=blocked_ids)


@router.put("/{user_id}/blocks/{target_id}", status_code=204)
async def block_user(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
):
    _, owner, _ = resolved
    if target_id == owner.id:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_TARGET", "message": "You cannot block yourself."}})
    await db.execute(sqlite_insert(blocks).values(user_id=owner.id, blocked_id=target_id).on_conflict_do_nothing())
    await db.commit()
    await dispatch(events.block_add(user_id=owner.id, target_id=target_id), user_ids=[owner.id, target_id], db=db)


@router.delete("/{user_id}/blocks/{target_id}", status_code=204)
async def unblock_user(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
):
    _, owner, _ = resolved
    await db.execute(delete(blocks).where(blocks.c.user_id == owner.id, blocks.c.blocked_id == target_id))
    await db.commit()
    await dispatch(events.block_remove(user_id=owner.id, target_id=target_id), user_ids=[owner.id, target_id], db=db)


@router.get("/{user_id}/friends")
async def list_friends(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
) -> FriendListResponse:
    _, owner, _ = resolved
    limit = min(limit, config.limits.page_limit_friends)
    query = (
        select(User, friends.c.status)
        .join(friends, friends.c.friend_id == User.id)
        .where(friends.c.user_id == owner.id)
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
    return FriendListResponse(items=items, cursor=cursor)


@router.put("/{user_id}/friends/{target_id}", status_code=204)
async def add_friend(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
):
    _, owner, _ = resolved
    if target_id == owner.id:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_TARGET", "message": "You cannot add yourself as a friend."}})
    from datetime import datetime, timezone
    await db.execute(sqlite_insert(friends).values(user_id=owner.id, friend_id=target_id, status="pending", created_at=datetime.now(timezone.utc)).on_conflict_do_nothing())
    await db.commit()
    await dispatch(events.friend_request(user_id=owner.id, target_id=target_id), user_ids=[owner.id, target_id], db=db)


@router.post("/{user_id}/friends/{target_id}/accept", status_code=204)
async def accept_friend(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
):
    _, owner, _ = resolved
    from datetime import datetime, timezone
    row = await db.execute(
        select(friends).where(friends.c.user_id == target_id, friends.c.friend_id == owner.id, friends.c.status == "pending")
    )
    if row.first() is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "REQUEST_NOT_FOUND", "message": "No pending friend request from this user."}})
    from sqlalchemy import update
    await db.execute(
        update(friends).where(friends.c.user_id == target_id, friends.c.friend_id == owner.id).values(status="accepted")
    )
    await db.execute(sqlite_insert(friends).values(user_id=owner.id, friend_id=target_id, status="accepted", created_at=datetime.now(timezone.utc)).on_conflict_do_nothing())
    await db.commit()
    await dispatch(events.friend_add(user_id=owner.id, target_id=target_id), user_ids=[owner.id, target_id], db=db)


@router.post("/{user_id}/friends/{target_id}/reject", status_code=204)
async def reject_friend(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
):
    _, owner, _ = resolved
    result = await db.execute(
        delete(friends).where(friends.c.user_id == target_id, friends.c.friend_id == owner.id, friends.c.status == "pending")
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": {"code": "REQUEST_NOT_FOUND", "message": "No pending friend request from this user."}})
    await db.commit()
    await dispatch(events.friend_reject(user_id=owner.id, target_id=target_id), user_ids=[owner.id, target_id], db=db)


@router.delete("/{user_id}/friends/{target_id}", status_code=204)
async def remove_friend(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
):
    _, owner, _ = resolved
    await db.execute(delete(friends).where(friends.c.user_id == owner.id, friends.c.friend_id == target_id))
    await db.execute(delete(friends).where(friends.c.user_id == target_id, friends.c.friend_id == owner.id))
    await db.commit()
    await dispatch(events.friend_remove(user_id=owner.id, target_id=target_id), user_ids=[owner.id, target_id], db=db)


@router.get("/{user_id}")
async def get_user(
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(),
) -> UserResponse:
    _, target, _ = resolved

    # Fetch remote profile for federated users and update cached fields
    if target.federated and target.home_domain:
        try:
            from vox.federation.client import fetch_remote_profile
            remote = await fetch_remote_profile(db, target.username)
            if remote:
                if remote.get("display_name"):
                    target.display_name = remote["display_name"]
                if remote.get("avatar_url"):
                    target.avatar = remote["avatar_url"]
                if remote.get("bio"):
                    target.bio = remote["bio"]
                await db.commit()
        except Exception:
            pass  # Fire-and-forget on failure

    role_ids = await get_user_role_ids(db, target.id)
    return UserResponse(user_id=target.id, username=target.username, display_name=target.display_name, avatar=target.avatar, bio=target.bio, roles=role_ids, created_at=int(target.created_at.timestamp()), federated=target.federated, home_domain=target.home_domain)


@router.patch("/{user_id}")
async def update_profile(
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
) -> UserResponse:
    _, target, _ = resolved
    changed = {}
    if body.display_name is not None:
        target.display_name = body.display_name
        changed["display_name"] = body.display_name
    if body.avatar is not None:
        target.avatar = body.avatar
        changed["avatar"] = body.avatar
    if body.bio is not None:
        target.bio = body.bio
        changed["bio"] = body.bio
    await db.commit()
    if changed:
        await dispatch(events.user_update(user_id=target.id, **changed), db=db)
    role_ids = await get_user_role_ids(db, target.id)
    return UserResponse(user_id=target.id, username=target.username, display_name=target.display_name, avatar=target.avatar, bio=target.bio, roles=role_ids, created_at=int(target.created_at.timestamp()), federated=target.federated, home_domain=target.home_domain)

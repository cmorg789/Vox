from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.auth.service import get_user_role_ids
from vox.db.models import Ban, Invite, User
from vox.permissions import BAN_MEMBERS, KICK_MEMBERS
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.members import (
    BanRequest,
    BanResponse,
    JoinRequest,
    MemberListResponse,
    MemberResponse,
    UpdateMemberRequest,
)

router = APIRouter(tags=["members"])


@router.get("/api/v1/members")
async def list_members(
    limit: int = 100,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MemberListResponse:
    query = select(User).where(User.active == True).order_by(User.id).limit(limit)
    if after is not None:
        query = query.where(User.id > after)
    result = await db.execute(query)
    users = result.scalars().all()
    items = []
    for u in users:
        role_ids = await get_user_role_ids(db, u.id)
        items.append(MemberResponse(user_id=u.id, display_name=u.display_name, avatar=u.avatar, nickname=u.nickname, role_ids=role_ids))
    cursor = str(users[-1].id) if users else None
    return MemberListResponse(items=items, cursor=cursor)


@router.post("/api/v1/members/@me/join", status_code=204)
async def join_server(
    body: JoinRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Invite).where(Invite.code == body.invite_code))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=422, detail={"error": {"code": "INVITE_INVALID", "message": "Invite code is not valid."}})
    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail={"error": {"code": "INVITE_EXPIRED", "message": "Invite has expired."}})
    if invite.max_uses and invite.uses >= invite.max_uses:
        raise HTTPException(status_code=422, detail={"error": {"code": "INVITE_INVALID", "message": "Invite has reached max uses."}})
    # Check ban
    ban = await db.execute(select(Ban).where(Ban.user_id == user.id))
    if ban.scalar_one_or_none() is not None:
        raise HTTPException(status_code=403, detail={"error": {"code": "BANNED", "message": "You are banned from this server."}})
    invite.uses += 1
    user.active = True
    await db.commit()
    await dispatch(gw.member_join(user_id=user.id, display_name=user.display_name))


@router.delete("/api/v1/members/@me", status_code=204)
async def leave_server(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user.active = False
    await db.commit()
    await dispatch(gw.member_leave(user_id=user.id))


@router.patch("/api/v1/members/@me")
async def update_member(
    body: UpdateMemberRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberResponse:
    if body.nickname is not None:
        user.nickname = body.nickname
    await db.commit()
    await dispatch(gw.member_update(user_id=user.id, nickname=user.nickname))
    role_ids = await get_user_role_ids(db, user.id)
    return MemberResponse(user_id=user.id, display_name=user.display_name, avatar=user.avatar, nickname=user.nickname, role_ids=role_ids)


@router.delete("/api/v1/members/{user_id}", status_code=204)
async def kick_member(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(KICK_MEMBERS),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "User does not exist."}})
    target.active = False
    await db.commit()
    await dispatch(gw.member_leave(user_id=user_id))


# --- Bans ---

@router.put("/api/v1/bans/{user_id}")
async def ban_member(
    user_id: int,
    body: BanRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(BAN_MEMBERS),
) -> BanResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "User does not exist."}})
    target.active = False
    ban = Ban(user_id=user_id, reason=body.reason, created_at=datetime.now(timezone.utc))
    db.add(ban)
    await db.commit()
    await dispatch(gw.member_ban(user_id=user_id))
    return BanResponse(user_id=user_id, display_name=target.display_name, reason=body.reason)


@router.delete("/api/v1/bans/{user_id}", status_code=204)
async def unban_member(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(BAN_MEMBERS),
):
    await db.execute(delete(Ban).where(Ban.user_id == user_id))
    await db.commit()
    await dispatch(gw.member_unban(user_id=user_id))


@router.get("/api/v1/bans")
async def list_bans(
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(BAN_MEMBERS),
):
    result = await db.execute(select(Ban))
    bans = result.scalars().all()
    items = []
    for b in bans:
        u = (await db.execute(select(User).where(User.id == b.user_id))).scalar_one_or_none()
        items.append(BanResponse(user_id=b.user_id, display_name=u.display_name if u else None, reason=b.reason))
    return {"bans": items}

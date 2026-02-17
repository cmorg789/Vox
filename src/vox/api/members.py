from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.auth.service import get_user_role_ids
from vox.db.models import Ban, Invite, Message, Role, User, role_members
from vox.limits import limits
from vox.permissions import ADMINISTRATOR, BAN_MEMBERS, KICK_MEMBERS, has_permission, resolve_permissions
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.members import (
    BanRequest,
    BanResponse,
    JoinRequest,
    KickRequest,
    MemberListResponse,
    MemberResponse,
    UpdateMemberRequest,
)

router = APIRouter(tags=["members"])


async def get_highest_role_position(db: AsyncSession, user_id: int) -> float:
    """Return the highest role position for a user (lower number = higher rank).

    Returns infinity if the user has no roles, meaning they are outranked by everyone.
    """
    result = await db.execute(
        select(func.min(Role.position))
        .join(role_members, role_members.c.role_id == Role.id)
        .where(role_members.c.user_id == user_id)
    )
    pos = result.scalar()
    return pos if pos is not None else float("inf")


async def _check_role_hierarchy(db: AsyncSession, actor_id: int, target_id: int) -> None:
    """Raise 403 if the actor does not outrank the target in role hierarchy.

    Users with ADMINISTRATOR permission bypass this check.
    """
    resolved = await resolve_permissions(db, actor_id)
    if has_permission(resolved, ADMINISTRATOR):
        return
    actor_pos = await get_highest_role_position(db, actor_id)
    target_pos = await get_highest_role_position(db, target_id)
    if actor_pos >= target_pos:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "ROLE_HIERARCHY", "message": "You cannot perform this action on a member with an equal or higher role."}},
        )


@router.get("/api/v1/members")
async def list_members(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MemberListResponse:
    limit = min(limit, limits.page_limit_members)
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
    body: KickRequest | None = None,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(KICK_MEMBERS),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "User does not exist."}})
    await _check_role_hierarchy(db, actor.id, user_id)
    target.active = False
    from vox.audit import write_audit
    extra = {"reason": body.reason} if body and body.reason else None
    await write_audit(db, "member.kick", actor_id=actor.id, target_id=user_id, extra=extra)
    await db.commit()
    await dispatch(gw.member_leave(user_id=user_id))


# --- Bans ---

@router.put("/api/v1/bans/{user_id}")
async def ban_member(
    user_id: int,
    body: BanRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(BAN_MEMBERS),
) -> BanResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "User does not exist."}})
    await _check_role_hierarchy(db, actor.id, user_id)
    target.active = False
    ban = Ban(user_id=user_id, reason=body.reason, created_at=datetime.now(timezone.utc))
    db.add(ban)

    # Delete messages from the banned user within the specified time window
    if body.delete_msg_days and body.delete_msg_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=body.delete_msg_days)
        cutoff_ms = int(cutoff.timestamp() * 1000)
        # Find affected feed_ids for gateway events
        affected = await db.execute(
            select(Message.feed_id, Message.id)
            .where(Message.author_id == user_id, Message.timestamp >= cutoff_ms, Message.feed_id != None)
        )
        by_feed: dict[int, list[int]] = {}
        for row in affected:
            by_feed.setdefault(row.feed_id, []).append(row.id)

        await db.execute(
            delete(Message).where(Message.author_id == user_id, Message.timestamp >= cutoff_ms)
        )

        # Dispatch bulk delete events per feed
        for fid, msg_ids in by_feed.items():
            await dispatch(gw.message_bulk_delete(feed_id=fid, msg_ids=msg_ids))

    from vox.audit import write_audit
    await write_audit(db, "member.ban", actor_id=actor.id, target_id=user_id, extra={"reason": body.reason})
    await db.commit()
    await dispatch(gw.member_ban(user_id=user_id))
    return BanResponse(user_id=user_id, display_name=target.display_name, reason=body.reason, created_at=int(ban.created_at.timestamp()))


@router.delete("/api/v1/bans/{user_id}", status_code=204)
async def unban_member(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(BAN_MEMBERS),
):
    await db.execute(delete(Ban).where(Ban.user_id == user_id))
    from vox.audit import write_audit
    await write_audit(db, "member.unban", actor_id=actor.id, target_id=user_id)
    await db.commit()
    await dispatch(gw.member_unban(user_id=user_id))


@router.get("/api/v1/bans")
async def list_bans(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(BAN_MEMBERS),
):
    limit = min(limit, limits.page_limit_bans)
    query = select(Ban).order_by(Ban.user_id).limit(limit)
    if after is not None:
        query = query.where(Ban.user_id > after)
    result = await db.execute(query)
    bans = result.scalars().all()
    items = []
    for b in bans:
        u = (await db.execute(select(User).where(User.id == b.user_id))).scalar_one_or_none()
        items.append(BanResponse(user_id=b.user_id, display_name=u.display_name if u else None, reason=b.reason, created_at=int(b.created_at.timestamp())))
    cursor = str(bans[-1].user_id) if bans else None
    return {"items": items, "cursor": cursor}

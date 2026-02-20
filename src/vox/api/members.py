from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission, resolve_member
from vox.auth.service import get_user_role_ids
from vox.db.models import Ban, Invite, Message, Role, User, role_members
from vox.config import config
from vox.permissions import ADMINISTRATOR, BAN_MEMBERS, KICK_MEMBERS, MANAGE_NICKNAMES, has_permission, resolve_permissions
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.members import (
    BanListResponse,
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
    limit = min(limit, config.limits.page_limit_members)
    query = select(User).where(User.active == True).order_by(User.id).limit(limit)
    if after is not None:
        query = query.where(User.id > after)
    result = await db.execute(query)
    users = result.scalars().all()
    # Batch-fetch role assignments for all users to avoid N+1
    user_ids = [u.id for u in users]
    role_map: dict[int, list[int]] = {uid: [] for uid in user_ids}
    if user_ids:
        rm_result = await db.execute(
            select(role_members.c.user_id, role_members.c.role_id)
            .where(role_members.c.user_id.in_(user_ids))
        )
        for uid, rid in rm_result.all():
            role_map[uid].append(rid)
    items = []
    for u in users:
        items.append(MemberResponse(user_id=u.id, display_name=u.display_name, avatar=u.avatar, nickname=u.nickname, role_ids=role_map.get(u.id, [])))
    cursor = str(users[-1].id) if users else None
    return MemberListResponse(items=items, cursor=cursor)


@router.get("/api/v1/members/{user_id}")
async def get_member(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MemberResponse:
    result = await db.execute(select(User).where(User.id == user_id, User.active == True))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "Member does not exist."}})
    role_ids = await get_user_role_ids(db, user.id)
    return MemberResponse(user_id=user.id, display_name=user.display_name, avatar=user.avatar, nickname=user.nickname, role_ids=role_ids)


@router.post("/api/v1/members/join", status_code=204)
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
    # Atomic increment to prevent TOCTOU race on max_uses
    from sqlalchemy import update
    if invite.max_uses:
        result = await db.execute(
            update(Invite)
            .where(Invite.code == body.invite_code, Invite.uses < Invite.max_uses)
            .values(uses=Invite.uses + 1)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=422, detail={"error": {"code": "INVITE_INVALID", "message": "Invite has reached max uses."}})
    else:
        invite.uses += 1
    user.active = True
    await db.commit()
    await dispatch(gw.member_join(user_id=user.id, display_name=user.display_name), db=db)


@router.patch("/api/v1/members/{user_id}")
async def update_member(
    body: UpdateMemberRequest,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=MANAGE_NICKNAMES),
) -> MemberResponse:
    actor, target, is_self = resolved
    if not is_self:
        await _check_role_hierarchy(db, actor.id, target.id)
    if body.nickname is not None:
        target.nickname = body.nickname
    from vox.audit import write_audit
    await write_audit(db, "member.update", actor_id=actor.id, target_id=target.id, extra={"nickname": target.nickname})
    await db.commit()
    await dispatch(gw.member_update(user_id=target.id, nickname=target.nickname), db=db)
    role_ids = await get_user_role_ids(db, target.id)
    return MemberResponse(user_id=target.id, display_name=target.display_name, avatar=target.avatar, nickname=target.nickname, role_ids=role_ids)


@router.delete("/api/v1/members/{user_id}", status_code=204)
async def remove_member(
    body: KickRequest | None = None,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=KICK_MEMBERS),
):
    actor, target, is_self = resolved
    if is_self:
        target.active = False
        await db.commit()
        await dispatch(gw.member_leave(user_id=target.id), db=db)
        return
    await _check_role_hierarchy(db, actor.id, target.id)
    target.active = False
    from vox.audit import write_audit
    extra = {"reason": body.reason} if body and body.reason else None
    await write_audit(db, "member.kick", actor_id=actor.id, target_id=target.id, extra=extra)
    await db.commit()
    await dispatch(gw.member_leave(user_id=target.id), db=db)


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
            await dispatch(gw.message_bulk_delete(feed_id=fid, msg_ids=msg_ids), db=db)

    from vox.audit import write_audit
    await write_audit(db, "member.ban", actor_id=actor.id, target_id=user_id, extra={"reason": body.reason})
    await db.commit()
    await dispatch(gw.member_ban(user_id=user_id), db=db)
    return BanResponse(user_id=user_id, display_name=target.display_name, reason=body.reason, created_at=int(ban.created_at.timestamp()))


@router.delete("/api/v1/bans/{user_id}", status_code=204)
async def unban_member(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = require_permission(BAN_MEMBERS),
):
    result = await db.execute(delete(Ban).where(Ban.user_id == user_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": {"code": "BAN_NOT_FOUND", "message": "No ban exists for this user."}})
    target = await db.get(User, user_id)
    if target is not None and not target.active:
        target.active = True
    from vox.audit import write_audit
    await write_audit(db, "member.unban", actor_id=actor.id, target_id=user_id)
    await db.commit()
    await dispatch(gw.member_unban(user_id=user_id), db=db)


@router.get("/api/v1/bans")
async def list_bans(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(BAN_MEMBERS),
) -> BanListResponse:
    limit = min(limit, config.limits.page_limit_bans)
    query = (
        select(Ban, User)
        .outerjoin(User, User.id == Ban.user_id)
        .order_by(Ban.user_id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(Ban.user_id > after)
    result = await db.execute(query)
    rows = result.all()
    items = []
    for ban, user in rows:
        items.append(BanResponse(user_id=ban.user_id, display_name=user.display_name if user else None, reason=ban.reason, created_at=int(ban.created_at.timestamp())))
    cursor = str(rows[-1][0].user_id) if rows else None
    return BanListResponse(items=items, cursor=cursor)

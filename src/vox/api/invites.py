import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Config, ConfigKey, Invite, User
from vox.limits import limits
from vox.permissions import CREATE_INVITES
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.invites import CreateInviteRequest, InvitePreviewResponse, InviteResponse

router = APIRouter(prefix="/api/v1/invites", tags=["invites"])


@router.post("", status_code=201)
async def create_invite(
    body: CreateInviteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(CREATE_INVITES),
) -> InviteResponse:
    code = secrets.token_urlsafe(8)
    expires_at = None
    if body.max_age is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.max_age)
    invite = Invite(
        code=code,
        creator_id=user.id,
        feed_id=body.feed_id,
        max_uses=body.max_uses,
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )
    db.add(invite)
    from vox.audit import write_audit
    await write_audit(db, "invite.create", actor_id=user.id, extra={"code": code})
    await db.commit()
    await dispatch(gw.invite_create(code=code, creator_id=user.id, feed_id=body.feed_id))
    return InviteResponse(
        code=code,
        creator_id=user.id,
        feed_id=body.feed_id,
        max_uses=body.max_uses,
        uses=0,
        expires_at=int(expires_at.timestamp()) if expires_at else None,
    )


@router.delete("/{code}", status_code=204)
async def delete_invite(
    code: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    result = await db.execute(select(Invite).where(Invite.code == code))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "INVITE_INVALID", "message": "Invite not found."}})
    from vox.audit import write_audit
    await write_audit(db, "invite.delete", actor_id=actor.id, extra={"code": code})
    await db.delete(invite)
    await db.commit()
    await dispatch(gw.invite_delete(code=code))


@router.get("/{code}")
async def resolve_invite(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> InvitePreviewResponse:
    result = await db.execute(select(Invite).where(Invite.code == code))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "INVITE_INVALID", "message": "Invite not found."}})

    name_row = await db.execute(select(Config).where(Config.key == ConfigKey.SERVER_NAME))
    name = name_row.scalar_one_or_none()
    icon_row = await db.execute(select(Config).where(Config.key == ConfigKey.SERVER_ICON))
    icon = icon_row.scalar_one_or_none()
    count = (await db.execute(select(func.count()).select_from(User).where(User.active == True, User.federated == False))).scalar() or 0

    return InvitePreviewResponse(
        code=code,
        server_name=name.value if name else "Vox Server",
        server_icon=icon.value if icon else None,
        member_count=count,
    )


@router.get("")
async def list_invites(
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    limit = min(limit, limits.page_limit_invites)
    query = select(Invite).order_by(Invite.code).limit(limit)
    if after is not None:
        query = query.where(Invite.code > after)
    result = await db.execute(query)
    invites = result.scalars().all()
    items = [
        InviteResponse(
            code=i.code,
            creator_id=i.creator_id,
            feed_id=i.feed_id,
            max_uses=i.max_uses,
            uses=i.uses,
            expires_at=int(i.expires_at.timestamp()) if i.expires_at else None,
        )
        for i in invites
    ]
    cursor = invites[-1].code if invites else None
    return {"items": items, "cursor": cursor}

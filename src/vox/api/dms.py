import logging
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from vox.api.deps import get_current_user, get_db, resolve_member
from vox.permissions import ADMINISTRATOR
from vox.api.messages import _handle_slash_command, _msg_response, _snowflake
from vox.db.models import DM, DMReadState, DMSettings, File, Message, Reaction, User, dm_participants, message_attachments, role_members
from vox.config import config
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.gateway.notify import notify_for_message, notify_for_reaction
from vox.models.dms import (
    DMListResponse,
    DMResponse,
    OpenDMRequest,
    ReadReceiptRequest,
    UpdateGroupDMRequest,
)
from vox.models.messages import (
    EditMessageRequest,
    EditMessageResponse,
    MessageListResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from vox.models.users import DMSettingsResponse, UpdateDMSettingsRequest

router = APIRouter(tags=["dms"])
logger = logging.getLogger(__name__)


async def _dm_participant_ids(db: AsyncSession, dm_id: int) -> list[int]:
    result = await db.execute(select(dm_participants.c.user_id).where(dm_participants.c.dm_id == dm_id))
    return list(result.scalars().all())


def require_dm_participant():
    """FastAPI dependency factory: raises 403 if user is not a DM participant."""

    async def checker(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> User:
        dm_id = int(request.path_params["dm_id"])
        pids = await _dm_participant_ids(db, dm_id)
        if user.id not in pids:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}},
            )
        return user

    return Depends(checker)


@router.post("/api/v1/dms", status_code=201)
async def open_dm(
    body: OpenDMRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DMResponse:
    if body.recipient_id is not None:
        # 1:1 DM - check if one already exists
        existing = await db.execute(
            select(dm_participants.c.dm_id)
            .where(dm_participants.c.user_id == user.id)
            .intersect(
                select(dm_participants.c.dm_id).where(dm_participants.c.user_id == body.recipient_id)
            )
        )
        existing_dm_id = existing.scalar_one_or_none()
        if existing_dm_id is not None:
            dm = (await db.execute(select(DM).where(DM.id == existing_dm_id))).scalar_one()
            if not dm.is_group:
                pids = await _dm_participant_ids(db, dm.id)
                return DMResponse(dm_id=dm.id, participant_ids=pids, is_group=False, icon=dm.icon)

        # Block check — recipient has blocked sender
        from vox.db.models import blocks, friends
        block_check = await db.execute(
            select(blocks.c.user_id).where(blocks.c.user_id == body.recipient_id, blocks.c.blocked_id == user.id)
        )
        if block_check.scalar_one_or_none() is not None:
            raise HTTPException(status_code=403, detail={"error": {"code": "USER_BLOCKED", "message": "You cannot DM this user."}})

        # DM permission check
        settings_result = await db.execute(select(DMSettings).where(DMSettings.user_id == body.recipient_id))
        dm_settings = settings_result.scalar_one_or_none()
        dm_perm = dm_settings.dm_permission if dm_settings else "everyone"

        if dm_perm == "nobody":
            raise HTTPException(status_code=403, detail={"error": {"code": "DM_PERMISSION_DENIED", "message": "This user does not accept DMs."}})
        elif dm_perm == "friends_only":
            friend_check = await db.execute(
                select(friends.c.user_id).where(friends.c.user_id == body.recipient_id, friends.c.friend_id == user.id, friends.c.status == "accepted")
            )
            if friend_check.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail={"error": {"code": "DM_PERMISSION_DENIED", "message": "This user only accepts DMs from friends."}})
        elif dm_perm == "mutual_servers":
            mutual = await db.execute(
                select(role_members.c.role_id)
                .where(role_members.c.user_id == user.id)
                .intersect(
                    select(role_members.c.role_id).where(role_members.c.user_id == body.recipient_id)
                )
            )
            if mutual.first() is None:
                raise HTTPException(status_code=403, detail={"error": {"code": "DM_PERMISSION_DENIED", "message": "You must share a server with this user to send them a DM."}})

        dm = DM(is_group=False, created_at=datetime.now(timezone.utc))
        db.add(dm)
        await db.flush()
        await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=user.id))
        await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=body.recipient_id))
        await db.commit()
        pids = [user.id, body.recipient_id]
        await dispatch(gw.dm_create(dm_id=dm.id, participant_ids=pids, is_group=False), user_ids=pids, db=db)

        # Subscribe to federated user's presence if applicable
        try:
            recipient = (await db.execute(select(User).where(User.id == body.recipient_id))).scalar_one_or_none()
            if recipient and recipient.federated and recipient.home_domain:
                from vox.federation.client import subscribe_presence
                await subscribe_presence(db, recipient.username)
        except (httpx.HTTPError, ConnectionError, OSError):
            pass  # Fire-and-forget

        return DMResponse(dm_id=dm.id, participant_ids=pids, is_group=False, icon=dm.icon)

    elif body.recipient_ids is not None:
        # Group DM - deduplicate recipient list
        all_ids = list(dict.fromkeys([user.id] + body.recipient_ids))
        if len(all_ids) > config.limits.group_dm_recipients_max:
            raise HTTPException(status_code=400, detail={"error": {"code": "TOO_MANY_RECIPIENTS", "message": f"Group DMs are limited to {config.limits.group_dm_recipients_max} participants."}})
        # Validate all recipient IDs exist
        existing = await db.execute(select(User.id).where(User.id.in_(body.recipient_ids)))
        valid_ids = {row[0] for row in existing.all()}
        invalid = set(body.recipient_ids) - valid_ids
        if invalid:
            raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": f"User(s) not found: {sorted(invalid)}"}})
        dm = DM(is_group=True, name=body.name, created_at=datetime.now(timezone.utc))
        db.add(dm)
        await db.flush()
        for uid in all_ids:
            await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=uid))
        await db.commit()
        await dispatch(gw.dm_create(dm_id=dm.id, participant_ids=all_ids, is_group=True, name=body.name), user_ids=all_ids, db=db)
        return DMResponse(dm_id=dm.id, participant_ids=all_ids, is_group=True, name=body.name, icon=dm.icon)

    raise HTTPException(status_code=400, detail={"error": {"code": "PROTOCOL_VERSION_MISMATCH", "message": "Provide recipient_id or recipient_ids."}})


@router.get("/api/v1/dms")
async def list_dms(
    limit: int = Query(default=100, ge=1, le=1000),
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DMListResponse:
    limit = min(limit, config.limits.page_limit_dms)
    query = (
        select(DM)
        .join(dm_participants, dm_participants.c.dm_id == DM.id)
        .where(dm_participants.c.user_id == user.id)
        .order_by(DM.id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(DM.id > after)
    result = await db.execute(query)
    dms = result.scalars().all()
    if not dms:
        return DMListResponse(items=[], cursor=None)
    # Batch-load all participants to avoid N+1
    dm_ids = [dm.id for dm in dms]
    parts_result = await db.execute(
        select(dm_participants.c.dm_id, dm_participants.c.user_id)
        .where(dm_participants.c.dm_id.in_(dm_ids))
    )
    pids_map: dict[int, list[int]] = {did: [] for did in dm_ids}
    for did, uid in parts_result.all():
        pids_map[did].append(uid)
    items = [
        DMResponse(dm_id=dm.id, participant_ids=pids_map.get(dm.id, []), is_group=dm.is_group, name=dm.name, icon=dm.icon)
        for dm in dms
    ]
    cursor = str(dms[-1].id) if dms else None
    return DMListResponse(items=items, cursor=cursor)


@router.delete("/api/v1/dms/{dm_id}", status_code=204)
async def close_dm(
    dm_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = require_dm_participant(),
):
    # Get remaining participants before removal
    remaining = [uid for uid in await _dm_participant_ids(db, dm_id) if uid != user.id]
    # Remove user from participants (hides DM, doesn't delete messages)
    await db.execute(delete(dm_participants).where(dm_participants.c.dm_id == dm_id, dm_participants.c.user_id == user.id))
    await db.commit()
    if remaining:
        await dispatch(gw.dm_recipient_remove(dm_id=dm_id, user_id=user.id), user_ids=remaining, db=db)


@router.patch("/api/v1/dms/{dm_id}")
async def update_group_dm(
    dm_id: int,
    body: UpdateGroupDMRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_dm_participant(),
) -> DMResponse:
    result = await db.execute(select(DM).where(DM.id == dm_id))
    dm = result.scalar_one_or_none()
    if dm is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "DM not found."}})
    changed = {}
    if body.name is not None:
        dm.name = body.name
        changed["name"] = body.name
    if body.icon is not None:
        dm.icon = body.icon
        changed["icon"] = body.icon
    await db.commit()
    pids = await _dm_participant_ids(db, dm.id)
    if changed:
        await dispatch(gw.dm_update(dm_id=dm_id, **changed), user_ids=pids, db=db)
    return DMResponse(dm_id=dm.id, participant_ids=pids, is_group=dm.is_group, name=dm.name, icon=dm.icon)


@router.put("/api/v1/dms/{dm_id}/recipients/{user_id}", status_code=204)
async def add_dm_recipient(
    dm_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(get_current_user),
):
    dm = (await db.execute(select(DM).where(DM.id == dm_id))).scalar_one_or_none()
    if dm is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "DM not found."}})
    if not dm.is_group:
        raise HTTPException(status_code=400, detail={"error": {"code": "NOT_GROUP_DM", "message": "Cannot add recipients to a 1:1 DM. Convert to group first."}})
    pids = await _dm_participant_ids(db, dm_id)
    if caller.id not in pids:
        raise HTTPException(status_code=403, detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}})
    if len(pids) >= config.limits.group_dm_recipients_max:
        raise HTTPException(status_code=400, detail={"error": {"code": "TOO_MANY_RECIPIENTS", "message": f"Group DMs are limited to {config.limits.group_dm_recipients_max} participants."}})
    await db.execute(sqlite_insert(dm_participants).values(dm_id=dm_id, user_id=user_id).on_conflict_do_nothing())
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.dm_recipient_add(dm_id=dm_id, user_id=user_id), user_ids=pids, db=db)


@router.delete("/api/v1/dms/{dm_id}/recipients/{user_id}", status_code=204)
async def remove_dm_recipient(
    dm_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(get_current_user),
):
    pids = await _dm_participant_ids(db, dm_id)
    if caller.id not in pids:
        raise HTTPException(status_code=403, detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}})
    if user_id == caller.id:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_OPERATION", "message": "Use DELETE /dms/{dm_id} to leave a DM."}})
    await db.execute(delete(dm_participants).where(dm_participants.c.dm_id == dm_id, dm_participants.c.user_id == user_id))
    await db.commit()
    await dispatch(gw.dm_recipient_remove(dm_id=dm_id, user_id=user_id), user_ids=pids, db=db)


@router.post("/api/v1/dms/{dm_id}/convert-to-group", status_code=200)
async def convert_dm_to_group(
    dm_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DMResponse:
    dm = (await db.execute(select(DM).where(DM.id == dm_id))).scalar_one_or_none()
    if dm is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SPACE_NOT_FOUND", "message": "DM not found."}})
    pids = await _dm_participant_ids(db, dm_id)
    if user.id not in pids:
        raise HTTPException(status_code=403, detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}})
    if not dm.is_group:
        dm.is_group = True
        await db.commit()
        await dispatch(gw.dm_update(dm_id=dm_id, is_group=True), user_ids=pids, db=db)
    return DMResponse(dm_id=dm.id, participant_ids=pids, is_group=dm.is_group, name=dm.name, icon=dm.icon)


@router.post("/api/v1/dms/{dm_id}/read", status_code=204)
async def send_read_receipt(
    dm_id: int,
    body: ReadReceiptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_dm_participant(),
):
    result = await db.execute(select(DMReadState).where(DMReadState.user_id == user.id, DMReadState.dm_id == dm_id))
    state = result.scalar_one_or_none()
    if state:
        state.last_read_msg_id = body.up_to_msg_id
    else:
        db.add(DMReadState(user_id=user.id, dm_id=dm_id, last_read_msg_id=body.up_to_msg_id))
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.dm_read_notify(dm_id=dm_id, user_id=user.id, up_to_msg_id=body.up_to_msg_id), user_ids=pids, db=db)

    # Federated read receipt relay
    try:
        from vox.federation.client import relay_read_receipt
        from vox.federation.service import get_our_domain

        our_domain = await get_our_domain(db)
        if our_domain:
            participants = await db.execute(
                select(User).join(dm_participants, dm_participants.c.user_id == User.id)
                .where(dm_participants.c.dm_id == dm_id, User.federated == True)
            )
            from_addr = f"{user.username}@{our_domain}"
            for fed_user in participants.scalars().all():
                if fed_user.home_domain:
                    await relay_read_receipt(db, from_addr, fed_user.username, body.up_to_msg_id)
    except (httpx.HTTPError, ConnectionError, OSError):
        pass  # Fire-and-forget


# --- DM Messages ---

@router.post("/api/v1/dms/{dm_id}/messages", status_code=201)
async def send_dm_message(
    dm_id: int,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_dm_participant(),
) -> SendMessageResponse:
    # Empty message validation
    if not (body.body and body.body.strip()) and not body.attachments:
        raise HTTPException(status_code=400, detail={"error": {"code": "EMPTY_MESSAGE", "message": "Message must have body or attachments."}})
    if body.body and len(body.body) > config.limits.message_body_max:
        raise HTTPException(status_code=400, detail={"error": {"code": "MESSAGE_TOO_LARGE", "message": f"Message body exceeds maximum of {config.limits.message_body_max} characters."}})
    # Slash command interception
    intercepted = await _handle_slash_command(body.body, user, feed_id=None, dm_id=dm_id, db=db)
    if intercepted is not None:
        return intercepted
    msg_id = await _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(id=msg_id, dm_id=dm_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to)
    db.add(msg)
    await db.flush()
    attachment_dicts = []
    if body.attachments:
        for file_id in body.attachments:
            f = (await db.execute(select(File).where(File.id == file_id))).scalar_one_or_none()
            if f is None:
                raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_ATTACHMENT", "message": f"File {file_id} not found."}})
            if f.uploader_id != user.id and f.dm_id != dm_id:
                raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this file."}})
            await db.execute(message_attachments.insert().values(msg_id=msg_id, file_id=file_id))
            attachment_dicts.append({"file_id": f.id, "name": f.name, "size": f.size, "mime": f.mime, "url": f.url})
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.message_create(msg_id=msg_id, dm_id=dm_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to, mentions=body.mentions, attachments=attachment_dicts or None), user_ids=pids, db=db)
    await notify_for_message(db, msg_id=msg_id, feed_id=None, thread_id=None, dm_id=dm_id, author_id=user.id, body=body.body, reply_to=body.reply_to, mentions=body.mentions)

    # Outbound federation relay for federated participants
    try:
        from vox.federation.client import relay_dm_message
        from vox.federation.service import check_federation_allowed, get_our_domain

        our_domain = await get_our_domain(db)
        if our_domain:
            participants = await db.execute(
                select(User).join(dm_participants, dm_participants.c.user_id == User.id).where(dm_participants.c.dm_id == dm_id)
            )
            for participant in participants.scalars().all():
                if participant.federated and participant.home_domain:
                    if not await check_federation_allowed(db, participant.home_domain, "outbound"):
                        continue  # Skip blocked domains
                    from_address = f"{user.username}@{our_domain}"
                    to_address = participant.username  # Already user@domain for fed users
                    await relay_dm_message(db, from_address, to_address, body.body or "")
    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        logger.warning("Federation DM relay failed: %s", exc)

    return SendMessageResponse(msg_id=msg_id, timestamp=ts)


@router.get("/api/v1/dms/{dm_id}/messages")
async def get_dm_messages(
    dm_id: int,
    limit: int = Query(default=50, ge=1, le=1000),
    before: int | None = None,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = require_dm_participant(),
) -> MessageListResponse:
    limit = min(limit, config.limits.page_limit_messages)
    query = select(Message).options(selectinload(Message.attachments)).where(Message.dm_id == dm_id).order_by(Message.id.desc()).limit(limit)
    if before is not None:
        query = query.where(Message.id < before)
    if after is not None:
        query = query.where(Message.id > after)
    result = await db.execute(query)
    return MessageListResponse(messages=[_msg_response(m) for m in result.scalars().all()])


@router.patch("/api/v1/dms/{dm_id}/messages/{msg_id}")
async def edit_dm_message(
    dm_id: int,
    msg_id: int,
    body: EditMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_dm_participant(),
) -> EditMessageResponse:
    result = await db.execute(select(Message).where(Message.id == msg_id, Message.dm_id == dm_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    if msg.author_id != user.id:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You can only edit your own messages."}})
    msg.body = body.body
    msg.edit_timestamp = int(time.time() * 1000)
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.message_update(msg_id=msg.id, dm_id=dm_id, body=body.body, edit_timestamp=msg.edit_timestamp), user_ids=pids, db=db)
    return EditMessageResponse(msg_id=msg.id, edit_timestamp=msg.edit_timestamp)


@router.delete("/api/v1/dms/{dm_id}/messages/{msg_id}", status_code=204)
async def delete_dm_message(
    dm_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = require_dm_participant(),
):
    result = await db.execute(select(Message).where(Message.id == msg_id, Message.dm_id == dm_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    if msg.author_id != user.id:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "You can only delete your own DM messages."}})
    await db.delete(msg)
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.message_delete(msg_id=msg_id, dm_id=dm_id), user_ids=pids, db=db)


# --- DM Reactions ---

@router.put("/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/{emoji}", status_code=204)
async def add_dm_reaction(
    dm_id: int,
    msg_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    pids = await _dm_participant_ids(db, dm_id)
    if user.id not in pids:
        raise HTTPException(status_code=403, detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}})
    msg = (await db.execute(select(Message).where(Message.id == msg_id, Message.dm_id == dm_id))).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    stmt = sqlite_insert(Reaction).values(msg_id=msg_id, user_id=user.id, emoji=emoji).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()
    await dispatch(gw.message_reaction_add(msg_id=msg_id, user_id=user.id, emoji=emoji), user_ids=pids, db=db)
    await notify_for_reaction(db, msg_id=msg_id, reactor_id=user.id, emoji=emoji)


@router.delete("/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/{emoji}", status_code=204)
async def remove_dm_reaction(
    dm_id: int,
    msg_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pids = await _dm_participant_ids(db, dm_id)
    if user.id not in pids:
        raise HTTPException(status_code=403, detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}})
    msg = (await db.execute(select(Message).where(Message.id == msg_id, Message.dm_id == dm_id))).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message does not exist."}})
    await db.execute(
        delete(Reaction).where(Reaction.msg_id == msg_id, Reaction.user_id == user.id, Reaction.emoji == emoji)
    )
    await db.commit()
    await dispatch(gw.message_reaction_remove(msg_id=msg_id, user_id=user.id, emoji=emoji), user_ids=pids, db=db)


# --- DM Settings ---

@router.get("/api/v1/users/{user_id}/dm-settings")
async def get_dm_settings(
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
) -> DMSettingsResponse:
    _, target, _ = resolved
    result = await db.execute(select(DMSettings).where(DMSettings.user_id == target.id))
    settings = result.scalar_one_or_none()
    return DMSettingsResponse(dm_permission=settings.dm_permission if settings else "everyone")


@router.patch("/api/v1/users/{user_id}/dm-settings")
async def update_dm_settings(
    body: UpdateDMSettingsRequest,
    db: AsyncSession = Depends(get_db),
    resolved: tuple[User, User, bool] = resolve_member(other_perm=ADMINISTRATOR),
) -> DMSettingsResponse:
    _, target, _ = resolved
    result = await db.execute(select(DMSettings).where(DMSettings.user_id == target.id))
    settings = result.scalar_one_or_none()
    if settings:
        settings.dm_permission = body.dm_permission
    else:
        db.add(DMSettings(user_id=target.id, dm_permission=body.dm_permission))
    await db.commit()
    return DMSettingsResponse(dm_permission=body.dm_permission)

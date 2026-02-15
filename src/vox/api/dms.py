import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vox.api.deps import get_current_user, get_db
from vox.api.messages import _msg_response, _snowflake
from vox.db.models import DM, DMReadState, DMSettings, File, Message, User, dm_participants, message_attachments
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
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


async def _dm_participant_ids(db: AsyncSession, dm_id: int) -> list[int]:
    result = await db.execute(select(dm_participants.c.user_id).where(dm_participants.c.dm_id == dm_id))
    return list(result.scalars().all())


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
                return DMResponse(dm_id=dm.id, participant_ids=pids, is_group=False)

        dm = DM(is_group=False, created_at=datetime.now(timezone.utc))
        db.add(dm)
        await db.flush()
        await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=user.id))
        await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=body.recipient_id))
        await db.commit()
        pids = [user.id, body.recipient_id]
        await dispatch(gw.dm_create(dm_id=dm.id, participant_ids=pids, is_group=False), user_ids=pids)
        return DMResponse(dm_id=dm.id, participant_ids=pids, is_group=False)

    elif body.recipient_ids is not None:
        # Group DM
        dm = DM(is_group=True, name=body.name, created_at=datetime.now(timezone.utc))
        db.add(dm)
        await db.flush()
        all_ids = [user.id] + body.recipient_ids
        for uid in all_ids:
            await db.execute(dm_participants.insert().values(dm_id=dm.id, user_id=uid))
        await db.commit()
        await dispatch(gw.dm_create(dm_id=dm.id, participant_ids=all_ids, is_group=True, name=body.name), user_ids=all_ids)
        return DMResponse(dm_id=dm.id, participant_ids=all_ids, is_group=True, name=body.name)

    raise HTTPException(status_code=400, detail={"error": {"code": "PROTOCOL_VERSION_MISMATCH", "message": "Provide recipient_id or recipient_ids."}})


@router.get("/api/v1/dms")
async def list_dms(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DMListResponse:
    result = await db.execute(
        select(DM).join(dm_participants, dm_participants.c.dm_id == DM.id).where(dm_participants.c.user_id == user.id)
    )
    dms = result.scalars().all()
    items = []
    for dm in dms:
        pids = await _dm_participant_ids(db, dm.id)
        items.append(DMResponse(dm_id=dm.id, participant_ids=pids, is_group=dm.is_group, name=dm.name))
    return DMListResponse(dms=items)


@router.delete("/api/v1/dms/{dm_id}", status_code=204)
async def close_dm(
    dm_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Remove user from participants (hides DM, doesn't delete messages)
    await db.execute(delete(dm_participants).where(dm_participants.c.dm_id == dm_id, dm_participants.c.user_id == user.id))
    await db.commit()


@router.patch("/api/v1/dms/{dm_id}")
async def update_group_dm(
    dm_id: int,
    body: UpdateGroupDMRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
        await dispatch(gw.dm_update(dm_id=dm_id, **changed), user_ids=pids)
    return DMResponse(dm_id=dm.id, participant_ids=pids, is_group=dm.is_group, name=dm.name)


@router.put("/api/v1/dms/{dm_id}/recipients/{user_id}", status_code=204)
async def add_dm_recipient(
    dm_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await db.execute(dm_participants.insert().values(dm_id=dm_id, user_id=user_id))
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.dm_recipient_add(dm_id=dm_id, user_id=user_id), user_ids=pids)


@router.delete("/api/v1/dms/{dm_id}/recipients/{user_id}", status_code=204)
async def remove_dm_recipient(
    dm_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    pids = await _dm_participant_ids(db, dm_id)
    await db.execute(delete(dm_participants).where(dm_participants.c.dm_id == dm_id, dm_participants.c.user_id == user_id))
    await db.commit()
    await dispatch(gw.dm_recipient_remove(dm_id=dm_id, user_id=user_id), user_ids=pids)


@router.post("/api/v1/dms/{dm_id}/read", status_code=204)
async def send_read_receipt(
    dm_id: int,
    body: ReadReceiptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(DMReadState).where(DMReadState.user_id == user.id, DMReadState.dm_id == dm_id))
    state = result.scalar_one_or_none()
    if state:
        state.last_read_msg_id = body.up_to_msg_id
    else:
        db.add(DMReadState(user_id=user.id, dm_id=dm_id, last_read_msg_id=body.up_to_msg_id))
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.dm_read_notify(dm_id=dm_id, user_id=user.id, up_to_msg_id=body.up_to_msg_id), user_ids=pids)


# --- DM Messages ---

@router.post("/api/v1/dms/{dm_id}/messages", status_code=201)
async def send_dm_message(
    dm_id: int,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SendMessageResponse:
    msg_id = _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(id=msg_id, dm_id=dm_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to)
    db.add(msg)
    await db.flush()
    if body.attachments:
        for file_id in body.attachments:
            f = (await db.execute(select(File).where(File.id == file_id))).scalar_one_or_none()
            if f is None:
                raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_ATTACHMENT", "message": f"File {file_id} not found."}})
            await db.execute(message_attachments.insert().values(msg_id=msg_id, file_id=file_id))
    await db.commit()
    pids = await _dm_participant_ids(db, dm_id)
    await dispatch(gw.message_create(msg_id=msg_id, dm_id=dm_id, author_id=user.id, body=body.body, timestamp=ts, reply_to=body.reply_to), user_ids=pids)
    return SendMessageResponse(msg_id=msg_id, timestamp=ts)


@router.get("/api/v1/dms/{dm_id}/messages")
async def get_dm_messages(
    dm_id: int,
    limit: int = 50,
    before: int | None = None,
    after: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageListResponse:
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
    user: User = Depends(get_current_user),
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
    await dispatch(gw.message_update(msg_id=msg.id, dm_id=dm_id, body=body.body, edit_timestamp=msg.edit_timestamp), user_ids=pids)
    return EditMessageResponse(msg_id=msg.id, edit_timestamp=msg.edit_timestamp)


@router.delete("/api/v1/dms/{dm_id}/messages/{msg_id}", status_code=204)
async def delete_dm_message(
    dm_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    await dispatch(gw.message_delete(msg_id=msg_id, dm_id=dm_id), user_ids=pids)


# --- DM Settings ---

@router.get("/api/v1/users/@me/dm-settings")
async def get_dm_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DMSettingsResponse:
    result = await db.execute(select(DMSettings).where(DMSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    return DMSettingsResponse(dm_permission=settings.dm_permission if settings else "everyone")


@router.patch("/api/v1/users/@me/dm-settings")
async def update_dm_settings(
    body: UpdateDMSettingsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DMSettingsResponse:
    result = await db.execute(select(DMSettings).where(DMSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    if settings:
        settings.dm_permission = body.dm_permission
    else:
        db.add(DMSettings(user_id=user.id, dm_permission=body.dm_permission))
    await db.commit()
    return DMSettingsResponse(dm_permission=body.dm_permission)

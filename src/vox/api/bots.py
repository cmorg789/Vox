import json
import time

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.api.messages import _snowflake
from vox.db.models import Bot, BotCommand, Message, User
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.interactions import consume
from vox.models.bots import (
    CommandResponse,
    ComponentInteractionRequest,
    DeregisterCommandsRequest,
    InteractionResponse,
    RegisterCommandsRequest,
)
from vox import interactions

router = APIRouter(tags=["bots"])


@router.put("/api/v1/bots/@me/commands")
async def register_commands(
    body: RegisterCommandsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Find the bot associated with this user
    result = await db.execute(select(Bot).where(Bot.user_id == user.id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Not a bot account."}})

    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    for cmd in body.commands:
        params_json = json.dumps([p.model_dump() for p in cmd.params]) if cmd.params else None
        stmt = sqlite_insert(BotCommand).values(
            bot_id=bot.id,
            name=cmd.name,
            description=cmd.description,
            params=params_json,
        ).on_conflict_do_update(
            index_elements=["bot_id", "name"],
            set_={"description": cmd.description, "params": params_json},
        )
        await db.execute(stmt)
    await db.commit()
    cmds = [{"name": c.name, "description": c.description, "params": json.loads(c.params) if c.params else []} for c in body.commands]
    await dispatch(gw.bot_commands_update(bot_id=bot.id, commands=cmds), db=db)
    return {"ok": True}


@router.get("/api/v1/bots/@me/commands")
async def list_bot_commands(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Bot).where(Bot.user_id == user.id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Not a bot account."}})
    result = await db.execute(select(BotCommand).where(BotCommand.bot_id == bot.id))
    commands = result.scalars().all()
    items = [CommandResponse(name=c.name, description=c.description, params=json.loads(c.params) if c.params else []) for c in commands]
    return {"commands": items}


@router.delete("/api/v1/bots/@me/commands")
async def deregister_commands(
    body: DeregisterCommandsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Bot).where(Bot.user_id == user.id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Not a bot account."}})

    for name in body.command_names:
        await db.execute(delete(BotCommand).where(BotCommand.bot_id == bot.id, BotCommand.name == name))
    await db.commit()
    await dispatch(gw.bot_commands_delete(bot_id=bot.id, command_names=body.command_names), db=db)
    return {"ok": True}


@router.get("/api/v1/commands")
async def list_commands(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(BotCommand))
    commands = result.scalars().all()
    items = []
    for c in commands:
        params = json.loads(c.params) if c.params else []
        items.append(CommandResponse(name=c.name, description=c.description, params=params))
    return {"commands": items}


@router.post("/api/v1/interactions/{interaction_id}/response", status_code=204)
async def respond_to_interaction(
    interaction_id: str,
    body: InteractionResponse,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interaction = consume(interaction_id)
    if interaction is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "INTERACTION_NOT_FOUND", "message": "Interaction not found or expired."}})

    # Verify the responding user is the bot's user account
    result = await db.execute(select(Bot).where(Bot.id == interaction.bot_id))
    bot = result.scalar_one_or_none()
    if bot is None or bot.user_id != user.id:
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Not authorized to respond to this interaction."}})

    if body.ephemeral:
        # Dispatch message_create only to the invoking user (not stored)
        msg_id = await _snowflake()
        ts = int(time.time() * 1000)
        await dispatch(
            gw.message_create(
                msg_id=msg_id,
                feed_id=interaction.feed_id,
                dm_id=interaction.dm_id,
                author_id=user.id,
                body=body.body,
                timestamp=ts,
            ),
            user_ids=[interaction.user_id],
            db=db,
        )
    else:
        # Create a real message in the feed/dm
        msg_id = await _snowflake()
        ts = int(time.time() * 1000)
        msg = Message(
            id=msg_id,
            feed_id=interaction.feed_id,
            dm_id=interaction.dm_id,
            author_id=user.id,
            body=body.body,
            timestamp=ts,
        )
        db.add(msg)
        await db.commit()
        await dispatch(
            gw.message_create(
                msg_id=msg_id,
                feed_id=interaction.feed_id,
                dm_id=interaction.dm_id,
                author_id=user.id,
                body=body.body,
                timestamp=ts,
            ),
            db=db,
        )

    return Response(status_code=204)


@router.post("/api/v1/interactions/component", status_code=204)
async def component_interaction(
    body: ComponentInteractionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Look up the message to find which bot owns it
    result = await db.execute(select(Message).where(Message.id == body.msg_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Message not found."}})

    # Find the bot whose user_id matches the message author
    result = await db.execute(select(Bot).where(Bot.user_id == msg.author_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=400, detail={"error": {"code": "NOT_BOT_MESSAGE", "message": "Message was not sent by a bot."}})

    interaction = interactions.create(
        type="button",
        command=None,
        params={"component_id": body.component_id},
        user_id=user.id,
        feed_id=msg.feed_id,
        dm_id=msg.dm_id,
        bot_id=bot.id,
    )

    await dispatch(
        gw.interaction_create({
            "id": interaction.id,
            "type": "button",
            "component_id": body.component_id,
            "user_id": user.id,
            "feed_id": msg.feed_id,
            "dm_id": msg.dm_id,
            "msg_id": body.msg_id,
        }),
        user_ids=[bot.user_id],
        db=db,
    )

    return Response(status_code=204)

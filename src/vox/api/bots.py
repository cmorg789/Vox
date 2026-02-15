import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.db.models import Bot, BotCommand, User
from vox.models.bots import (
    CommandResponse,
    DeregisterCommandsRequest,
    RegisterCommandsRequest,
)

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

    for cmd in body.commands:
        existing = await db.execute(select(BotCommand).where(BotCommand.bot_id == bot.id, BotCommand.name == cmd.name))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail={"error": {"code": "CMD_ALREADY_REGISTERED", "message": f"Command '{cmd.name}' already registered."}})
        db.add(BotCommand(
            bot_id=bot.id,
            name=cmd.name,
            description=cmd.description,
            params=json.dumps([p.model_dump() for p in cmd.params]) if cmd.params else None,
        ))
    await db.commit()
    return {"ok": True}


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

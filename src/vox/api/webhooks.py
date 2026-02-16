import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.api.messages import _snowflake
from vox.db.models import Message, User, Webhook
from vox.permissions import MANAGE_WEBHOOKS
from vox.models.bots import CreateWebhookRequest, ExecuteWebhookRequest, WebhookResponse
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch

router = APIRouter(tags=["webhooks"])


@router.post("/api/v1/feeds/{feed_id}/webhooks", status_code=201)
async def create_webhook(
    feed_id: int,
    body: CreateWebhookRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_WEBHOOKS),
) -> WebhookResponse:
    token = "whk_" + secrets.token_urlsafe(32)
    wh = Webhook(feed_id=feed_id, name=body.name, avatar=body.avatar, token=token, created_at=datetime.now(timezone.utc))
    db.add(wh)
    await db.flush()
    await db.commit()
    return WebhookResponse(webhook_id=wh.id, feed_id=feed_id, name=wh.name, token=token)


@router.get("/api/v1/feeds/{feed_id}/webhooks")
async def list_webhooks(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Webhook).where(Webhook.feed_id == feed_id))
    return {"webhooks": [WebhookResponse(webhook_id=w.id, feed_id=w.feed_id, name=w.name, token=w.token) for w in result.scalars().all()]}


@router.patch("/api/v1/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: int,
    body: CreateWebhookRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_WEBHOOKS),
) -> WebhookResponse:
    result = await db.execute(select(Webhook).where(Webhook.id == webhook_id))
    wh = result.scalar_one_or_none()
    if wh is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "WEBHOOK_NOT_FOUND", "message": "Webhook does not exist."}})
    wh.name = body.name
    if body.avatar is not None:
        wh.avatar = body.avatar
    await db.commit()
    return WebhookResponse(webhook_id=wh.id, feed_id=wh.feed_id, name=wh.name, token=wh.token)


@router.delete("/api/v1/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MANAGE_WEBHOOKS),
):
    result = await db.execute(select(Webhook).where(Webhook.id == webhook_id))
    wh = result.scalar_one_or_none()
    if wh is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "WEBHOOK_NOT_FOUND", "message": "Webhook does not exist."}})
    await db.delete(wh)
    await db.commit()


@router.post("/api/v1/webhooks/{webhook_id}/{token}", status_code=204)
async def execute_webhook(
    webhook_id: int,
    token: str,
    body: ExecuteWebhookRequest,
    db: AsyncSession = Depends(get_db),
):
    # No auth required — token in URL is the secret
    result = await db.execute(select(Webhook).where(Webhook.id == webhook_id, Webhook.token == token))
    wh = result.scalar_one_or_none()
    if wh is None:
        raise HTTPException(status_code=422, detail={"error": {"code": "WEBHOOK_TOKEN_INVALID", "message": "Webhook token is invalid."}})
    msg_id = await _snowflake()
    ts = int(time.time() * 1000)
    msg = Message(id=msg_id, feed_id=wh.feed_id, author_id=0, body=body.body, timestamp=ts)
    db.add(msg)
    await db.commit()
    await dispatch(gw.message_create(msg_id=msg_id, feed_id=wh.feed_id, author_id=0, body=body.body, timestamp=ts))

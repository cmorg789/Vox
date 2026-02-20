from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vox.api.deps import get_current_user, get_db
from vox.api.messages import _msg_response
from vox.db.models import Feed, Message, PermissionOverride, Pin, Role, User, dm_participants, message_attachments, role_members
from vox.config import config
from vox.db.engine import get_engine
from vox.models.messages import SearchResponse
from vox.permissions import VIEW_SPACE, has_permission

router = APIRouter(tags=["search"])


def _accessible_feed_ids_subquery(user_id: int):
    """Build a subquery of feed IDs the user can view via role permissions.

    This pushes permission filtering into the database rather than loading
    all feed IDs into memory.

    The logic mirrors resolve_permissions: start with the @everyone role's
    base permissions, layer on the user's role permissions, then apply
    per-feed permission overrides (allow/deny).
    """
    from sqlalchemy import and_, case, func, literal_column

    # Base permissions from @everyone role
    everyone_perms = (
        select(Role.permissions)
        .where(Role.position == 0, Role.name == "@everyone")
        .correlate_except(Role)
        .scalar_subquery()
    )

    # OR of all user role permissions (excluding @everyone which is handled above)
    user_role_perms = (
        select(func.coalesce(func.bit_or(Role.permissions), 0))
        .join(role_members, role_members.c.role_id == Role.id)
        .where(role_members.c.user_id == user_id)
        .correlate_except(Role, role_members)
        .scalar_subquery()
    )

    # Combined base = everyone | user_roles
    base_perms = everyone_perms.op("|")(user_role_perms)

    # Per-feed override: aggregate allow/deny for the user's roles + user-specific
    user_role_ids = (
        select(role_members.c.role_id)
        .where(role_members.c.user_id == user_id)
    )

    override_allow = (
        select(func.coalesce(func.bit_or(PermissionOverride.allow), 0))
        .where(
            PermissionOverride.space_type == "feed",
            PermissionOverride.space_id == Feed.id,
            (
                (PermissionOverride.target_type == "role") &
                (PermissionOverride.target_id.in_(user_role_ids))
            ) | (
                (PermissionOverride.target_type == "user") &
                (PermissionOverride.target_id == user_id)
            ),
        )
        .correlate(Feed)
        .scalar_subquery()
    )

    override_deny = (
        select(func.coalesce(func.bit_or(PermissionOverride.deny), 0))
        .where(
            PermissionOverride.space_type == "feed",
            PermissionOverride.space_id == Feed.id,
            (
                (PermissionOverride.target_type == "role") &
                (PermissionOverride.target_id.in_(user_role_ids))
            ) | (
                (PermissionOverride.target_type == "user") &
                (PermissionOverride.target_id == user_id)
            ),
        )
        .correlate(Feed)
        .scalar_subquery()
    )

    # final_perms = (base & ~deny) | allow
    # Check VIEW_SPACE bit
    view_bit = VIEW_SPACE
    final_perms = (base_perms.op("&")(~override_deny)).op("|")(override_allow)

    return (
        select(Feed.id)
        .where(final_perms.op("&")(view_bit) != 0)
    )


@router.get("/api/v1/messages/search")
async def search_messages(
    query: str,
    feed_id: int | None = None,
    dm_id: int | None = None,
    author_id: int | None = None,
    before: int | None = None,
    after: int | None = None,
    has_file: bool | None = None,
    has_embed: bool | None = None,
    pinned: bool | None = None,
    thread_id: int | None = None,
    limit: int = Query(default=25, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchResponse:
    limit = min(limit, config.limits.page_limit_search)

    # Detect dialect for FTS vs ILIKE
    dialect = get_engine().dialect.name

    if dialect == "postgresql":
        from sqlalchemy import func
        stmt = (
            select(Message)
            .options(selectinload(Message.attachments))
            .where(Message.search_vector.op("@@")(func.websearch_to_tsquery("english", query)))
            .order_by(Message.id.desc())
            .limit(limit)
        )
    else:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = (
            select(Message)
            .options(selectinload(Message.attachments))
            .where(Message.body.ilike(f"%{escaped}%", escape="\\"))
            .order_by(Message.id.desc())
            .limit(limit)
        )

    if dm_id is not None:
        # DM search: verify user is a participant
        pids_result = await db.execute(
            select(dm_participants.c.user_id).where(dm_participants.c.dm_id == dm_id)
        )
        pids = list(pids_result.scalars().all())
        if user.id not in pids:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "NOT_DM_PARTICIPANT", "message": "You are not a participant in this DM."}},
            )
        stmt = stmt.where(Message.dm_id == dm_id)
    else:
        if feed_id is not None:
            # Single feed: check permission for that feed only
            from vox.permissions import resolve_permissions
            perms = await resolve_permissions(db, user.id, space_type="feed", space_id=feed_id)
            if not has_permission(perms, VIEW_SPACE):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=403,
                    detail={"error": {"code": "MISSING_PERMISSIONS", "message": "You lack the required permissions."}},
                )
            stmt = stmt.where(Message.feed_id == feed_id)
        else:
            # All feeds: push permission check into the query via subquery
            if dialect == "postgresql":
                # Use the efficient subquery approach on PostgreSQL
                accessible = _accessible_feed_ids_subquery(user.id)
                stmt = stmt.where(Message.feed_id.in_(accessible))
            else:
                # SQLite lacks bit_or; fall back to Python-side filtering
                from vox.permissions import resolve_user_permissions_multi_space
                all_feeds = list((await db.execute(select(Feed.id).limit(5000))).scalars().all())
                if all_feeds:
                    perms_map = await resolve_user_permissions_multi_space(db, user.id, "feed", all_feeds)
                    accessible_feeds = [fid for fid in all_feeds if has_permission(perms_map.get(fid, 0), VIEW_SPACE)]
                else:
                    accessible_feeds = []
                stmt = stmt.where(Message.feed_id.in_(accessible_feeds))

    if thread_id is not None:
        stmt = stmt.where(Message.thread_id == thread_id)
    if author_id is not None:
        stmt = stmt.where(Message.author_id == author_id)
    if before is not None:
        stmt = stmt.where(Message.id < before)
    if after is not None:
        stmt = stmt.where(Message.id > after)
    if pinned is True:
        stmt = stmt.join(Pin, Pin.msg_id == Message.id)
    if has_file is True:
        stmt = stmt.join(message_attachments, message_attachments.c.msg_id == Message.id)
    if has_file is False:
        from sqlalchemy import not_, exists
        attachment_exists = select(message_attachments.c.msg_id).where(
            message_attachments.c.msg_id == Message.id
        ).exists()
        stmt = stmt.where(not_(attachment_exists))
    if has_embed is True:
        stmt = stmt.where(Message.embed != None)
    if has_embed is False:
        stmt = stmt.where(Message.embed == None)
    result = await db.execute(stmt)
    return SearchResponse(results=[_msg_response(m) for m in result.scalars().all()])

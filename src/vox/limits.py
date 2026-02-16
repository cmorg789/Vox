"""Runtime-configurable validation limits backed by DB Config table.

Uses pydantic-settings BaseSettings with a custom DB source so limits
can be overridden via:
  1. init kwargs  (highest priority)
  2. env vars     (VOX_LIMIT_USERNAME_MAX=64)
  3. DB Config    (key = "limit_username_max")
  4. field defaults (lowest priority)

Call ``load_limits(db)`` at startup (and after admin writes) to sync
the DB overrides into the in-memory singleton.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Module-level dict populated from Config table (async → sync bridge)
# ---------------------------------------------------------------------------
_db_overrides: dict[str, int] = {}


class DbLimitsSource(PydanticBaseSettingsSource):
    """Custom settings source that reads from ``_db_overrides``."""

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        return _db_overrides.get(field_name, None), field_name, False

    def __call__(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            val, _, _ = self.get_field_value(None, field_name)
            if val is not None:
                d[field_name] = val
        return d


class Limits(BaseSettings):
    model_config = {"env_prefix": "VOX_LIMIT_"}

    # --- Auth ---
    username_min: int = 1
    username_max: int = 32
    password_min: int = 8
    password_max: int = 128
    display_name_max: int = 64
    mfa_code_max: int = 32
    mfa_ticket_max: int = 256
    webauthn_field_max: int = 4096

    # --- Users / Profiles ---
    avatar_max: int = 512
    bio_max: int = 256
    nickname_max: int = 64

    # --- Messages ---
    message_body_max: int = 4000
    bulk_delete_max: int = 100

    # --- DMs ---
    group_dm_recipients_max: int = 10
    dm_name_max: int = 64
    dm_icon_max: int = 512

    # --- Channels (Feeds, Rooms, Categories, Threads) ---
    channel_name_min: int = 1
    channel_name_max: int = 64
    topic_max: int = 256

    # --- Roles ---
    role_name_min: int = 1
    role_name_max: int = 64

    # --- E2EE / Devices ---
    device_name_max: int = 64
    device_id_max: int = 128
    key_backup_max: int = 1_000_000
    max_devices: int = 10

    # --- Moderation ---
    report_reason_max: int = 64
    report_description_max: int = 2000
    admin_reason_max: int = 256
    kick_reason_max: int = 256
    ban_reason_max: int = 256
    ban_delete_days_max: int = 14

    # --- Invites ---
    invite_max_uses_max: int = 10000
    invite_max_age_max: int = 2592000  # 30 days in seconds

    # --- Server ---
    server_name_max: int = 64
    server_description_max: int = 256
    server_icon_max: int = 512

    # --- Bots / Webhooks ---
    webhook_name_max: int = 64
    command_name_max: int = 32
    command_description_max: int = 256

    # --- Federation ---
    federation_address_max: int = 256

    # --- Pagination ---
    page_limit_messages: int = 100
    page_limit_members: int = 200
    page_limit_dms: int = 100
    page_limit_reports: int = 100
    page_limit_audit_log: int = 100
    page_limit_emoji: int = 200
    page_limit_roles: int = 200
    page_limit_search: int = 100
    page_limit_invites: int = 100
    page_limit_bans: int = 200
    page_limit_friends: int = 200
    page_limit_stickers: int = 200

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, DbLimitsSource(settings_cls))


# Module-level singleton
limits = Limits()


# ---------------------------------------------------------------------------
# DB ↔ memory sync
# ---------------------------------------------------------------------------

async def load_limits(db: AsyncSession) -> None:
    """Load limit overrides from Config table into _db_overrides, then reload."""
    from vox.db.models import Config

    result = await db.execute(select(Config).where(Config.key.like("limit_%")))
    _db_overrides.clear()
    for row in result.scalars().all():
        name = row.key.removeprefix("limit_")  # "limit_username_max" → "username_max"
        _db_overrides[name] = int(row.value)
    limits.__init__()  # type: ignore[misc]  # In-place reload picks up new _db_overrides


async def save_limit(db: AsyncSession, name: str, value: int) -> None:
    """Write a single limit to DB + reload in-memory."""
    from vox.db.models import Config

    key = f"limit_{name}"
    result = await db.execute(select(Config).where(Config.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = str(value)
    else:
        db.add(Config(key=key, value=str(value)))
    _db_overrides[name] = value
    limits.__init__()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validator factories — used with Annotated[..., AfterValidator(...)]
# ---------------------------------------------------------------------------

def str_limit(*, min_attr: str | None = None, max_attr: str | None = None):
    """Returns a callable for AfterValidator that checks string length against limits.<attr>."""
    def _validate(v: str | None) -> str | None:
        if v is None:
            return v
        if min_attr and len(v) < getattr(limits, min_attr):
            raise ValueError(f"String should have at least {getattr(limits, min_attr)} character(s)")
        if max_attr and len(v) > getattr(limits, max_attr):
            raise ValueError(f"String should have at most {getattr(limits, max_attr)} character(s)")
        return v
    return _validate


def int_limit(*, ge: int | None = None, max_attr: str | None = None):
    """For numeric bounds — ge is a fixed floor, max_attr is runtime-configurable ceiling."""
    def _validate(v: int | None) -> int | None:
        if v is None:
            return v
        if ge is not None and v < ge:
            raise ValueError(f"Input should be greater than or equal to {ge}")
        if max_attr and v > getattr(limits, max_attr):
            raise ValueError(f"Input should be less than or equal to {getattr(limits, max_attr)}")
        return v
    return _validate


def list_limit(*, max_attr: str):
    """For list/array length constraints."""
    def _validate(v: list) -> list:
        if v is not None and len(v) > getattr(limits, max_attr):
            raise ValueError(f"List should have at most {getattr(limits, max_attr)} item(s)")
        return v
    return _validate

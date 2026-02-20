"""Unified server configuration backed by DB Config table.

Uses pydantic-settings ``BaseSettings`` sub-configs grouped under a top-level
``ServerConfig``.  All config values can be overridden via:

  1. env vars              (per-section prefix — highest priority)
  2. DB Config table rows  (application-level overrides via admin API)
  3. field defaults         (lowest priority)

Call ``load_config(db)`` at startup (and after admin writes) to sync
the DB overrides into the in-memory singleton.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Re-export validators so existing ``from vox.config import str_limit`` works.
from vox.validators import str_limit, int_limit, list_limit, check_mime  # noqa: F401

# ---------------------------------------------------------------------------
# Single flat store of raw DB values (async → sync bridge)
# ---------------------------------------------------------------------------
_db_values: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Generic DB settings source
# ---------------------------------------------------------------------------

class DbSource(PydanticBaseSettingsSource):
    """Reads values from ``_db_values`` using a per-class key map."""

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        key_map: dict[str, str] = getattr(self.settings_cls, "_DB_KEY_MAP", {})
        # Reverse: field_name -> db_key
        db_key = None
        for k, v in key_map.items():
            if v == field_name:
                db_key = k
                break
        if db_key is not None and db_key in _db_values:
            return _db_values[db_key], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            val, _, _ = self.get_field_value(None, field_name)
            if val is not None:
                d[field_name] = val
        return d


class _DbSettings(BaseSettings):
    """Base for all sub-configs: wires in DbSource so env > DB > defaults."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, DbSource(settings_cls))


# ---------------------------------------------------------------------------
# Sub-configs — all BaseSettings with DB key maps
# ---------------------------------------------------------------------------

class LimitsConfig(_DbSettings):
    model_config = {"env_prefix": "VOX_LIMIT_"}

    _DB_KEY_MAP: ClassVar[dict[str, str]] = {}  # auto-generated below

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
    max_pins_per_feed: int = 50

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

    # --- Emoji / Stickers ---
    emoji_name_max: int = 32

    # --- Federation ---
    federation_address_max: int = 256
    federation_presence_sub_limit: int = 1000

    # --- Relay ---
    relay_payload_max: int = 16384  # 16KB

    # --- Files ---
    file_upload_max_bytes: int = 25 * 1024 * 1024  # 25 MB

    # --- Gateway ---
    max_total_connections: int = 10000

    # --- Voice ---
    voice_room_max_members: int = 99

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


# Auto-generate the key map: limit_{field} -> field
LimitsConfig._DB_KEY_MAP = {f"limit_{f}": f for f in LimitsConfig.model_fields}


class ServerIdentityConfig(_DbSettings):
    model_config = {"env_prefix": "VOX_SERVER_"}

    _DB_KEY_MAP: ClassVar[dict[str, str]] = {
        "server_name": "name",
        "server_icon": "icon",
        "server_description": "description",
        "gateway_url": "gateway_url",
    }

    name: str = "Vox Server"
    icon: str | None = None
    description: str | None = None
    gateway_url: str = "wss://localhost/gateway"


class AuthConfig(_DbSettings):
    model_config = {"env_prefix": "VOX_AUTH_"}

    _DB_KEY_MAP: ClassVar[dict[str, str]] = {
        "session_ttl_days": "session_ttl_days",
    }

    session_ttl_days: int = 30


class MediaConfig(_DbSettings):
    model_config = {"env_prefix": "VOX_MEDIA_"}

    _DB_KEY_MAP: ClassVar[dict[str, str]] = {
        "media_url": "url",
        "media_tls_cert": "tls_cert",
        "media_tls_key": "tls_key",
        "allowed_file_mimes": "allowed_file_mimes",
        "allowed_emoji_mimes": "allowed_emoji_mimes",
        "allowed_sticker_mimes": "allowed_sticker_mimes",
    }

    url: str = "quic://localhost:4443"
    tls_cert: str | None = None  # Path to PEM cert file; omit to use self-signed
    tls_key: str | None = None   # Path to PEM key file; omit to use self-signed
    allowed_file_mimes: str = "image/*,video/*,audio/*,application/pdf,text/plain"
    allowed_emoji_mimes: str = "image/png,image/gif,image/webp"
    allowed_sticker_mimes: str = "image/png,image/gif,image/webp,image/apng"


class WebAuthnConfig(_DbSettings):
    model_config = {"env_prefix": "VOX_WEBAUTHN_"}

    _DB_KEY_MAP: ClassVar[dict[str, str]] = {
        "webauthn_rp_id": "rp_id",
        "webauthn_origin": "origin",
    }

    rp_id: str | None = None
    origin: str | None = None


class FederationConfig(_DbSettings):
    model_config = {"env_prefix": "VOX_FEDERATION_"}

    _DB_KEY_MAP: ClassVar[dict[str, str]] = {
        "federation_domain": "domain",
        "federation_policy": "policy",
        "federation_private_key": "private_key",
        "federation_public_key": "public_key",
    }
    # _SENSITIVE lists fields that must never be returned by admin config endpoints.
    _SENSITIVE: ClassVar[set[str]] = {"private_key"}

    domain: str | None = None
    policy: str = "open"
    private_key: str | None = None
    public_key: str | None = None


# ---------------------------------------------------------------------------
# Top-level ServerConfig
# ---------------------------------------------------------------------------

# All sub-config section names and their classes
_SECTIONS: dict[str, type[BaseSettings]] = {
    "server": ServerIdentityConfig,
    "auth": AuthConfig,
    "limits": LimitsConfig,
    "media": MediaConfig,
    "webauthn": WebAuthnConfig,
    "federation": FederationConfig,
}

# Reverse lookup: DB key -> section name
_KEY_TO_SECTION: dict[str, str] = {}
for _section_name, _cls in _SECTIONS.items():
    for _db_key in getattr(_cls, "_DB_KEY_MAP", {}):
        _KEY_TO_SECTION[_db_key] = _section_name


class ServerConfig(BaseModel):
    server: ServerIdentityConfig = ServerIdentityConfig()
    auth: AuthConfig = AuthConfig()
    limits: LimitsConfig = LimitsConfig()
    media: MediaConfig = MediaConfig()
    webauthn: WebAuthnConfig = WebAuthnConfig()
    federation: FederationConfig = FederationConfig()


# Module-level singletons
config = ServerConfig()


# ---------------------------------------------------------------------------
# Reload helpers
# ---------------------------------------------------------------------------

def _reload_section(section_name: str) -> None:
    """Rebuild a single sub-config from DB values + env."""
    new_obj = _SECTIONS[section_name]()
    setattr(config, section_name, new_obj)


def _reload_all() -> None:
    """Rebuild all sub-configs from ``_db_values`` + env."""
    for section_name in _SECTIONS:
        _reload_section(section_name)


# ---------------------------------------------------------------------------
# DB <-> memory sync
# ---------------------------------------------------------------------------

async def load_config(db: AsyncSession) -> None:
    """Load all config overrides from Config table into the in-memory singleton."""
    from vox.db.models import Config

    result = await db.execute(select(Config))
    _db_values.clear()
    for row in result.scalars().all():
        _db_values[row.key] = row.value
    _reload_all()


async def save_config_value(db: AsyncSession, key: str, value: str) -> None:
    """Write a single config value to DB + update in-memory.

    The caller is responsible for calling ``await db.commit()``.
    """
    from vox.db.models import Config

    result = await db.execute(select(Config).where(Config.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(Config(key=key, value=value))

    _db_values[key] = value

    # Reload only the affected section
    section = _KEY_TO_SECTION.get(key)
    if section:
        _reload_section(section)


async def save_limit(db: AsyncSession, name: str, value: int) -> None:
    """Write a single limit to DB + reload in-memory.

    The caller is responsible for calling ``await db.commit()``.
    """
    await save_config_value(db, f"limit_{name}", str(value))

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy.types import TypeDecorator


class TSVector(TypeDecorator):
    """A tsvector type that compiles to TSVECTOR on PostgreSQL, TEXT on other dialects."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import TSVECTOR
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


class Base(DeclarativeBase):
    pass


# --- Junction tables (no ORM class needed, just Table objects) ---

from sqlalchemy import Table

role_members = Table(
    "role_members",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
)

dm_participants = Table(
    "dm_participants",
    Base.metadata,
    Column("dm_id", Integer, ForeignKey("dms.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
)

message_attachments = Table(
    "message_attachments",
    Base.metadata,
    Column("msg_id", BigInteger, ForeignKey("messages.id"), primary_key=True),
    Column("file_id", String(255), ForeignKey("files.id"), primary_key=True),
)

feed_subscribers = Table(
    "feed_subscribers",
    Base.metadata,
    Column("feed_id", Integer, ForeignKey("feeds.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
)

thread_subscribers = Table(
    "thread_subscribers",
    Base.metadata,
    Column("thread_id", Integer, ForeignKey("threads.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
)

friends = Table(
    "friends",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("friend_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("status", String(20), server_default="accepted"),  # pending | accepted
    Column("created_at", DateTime),
    Index("ix_friends_friend_id", "friend_id"),
)

blocks = Table(
    "blocks",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("blocked_id", Integer, ForeignKey("users.id"), primary_key=True),
)


# --- Core ---


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", "home_domain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    federated: Mapped[bool] = mapped_column(Boolean)
    active: Mapped[bool] = mapped_column(Boolean, server_default="1")
    home_domain: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    avatar: Mapped[Optional[str]] = mapped_column(Text)
    bio: Mapped[Optional[str]] = mapped_column(String(255))
    nickname: Mapped[Optional[str]] = mapped_column(String(255))
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")
    roles: Mapped[list["Role"]] = relationship(secondary=role_members, back_populates="members")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    mfa_fail_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    user: Mapped["User"] = relationship(back_populates="sessions")


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


# --- Server Structure ---


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer)

    feeds: Mapped[list["Feed"]] = relationship(back_populates="category")
    rooms: Mapped[list["Room"]] = relationship(back_populates="category")


class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50))  # text, forum, announcement
    topic: Mapped[Optional[str]] = mapped_column(String(255))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    position: Mapped[int] = mapped_column(Integer)

    category: Mapped[Optional["Category"]] = relationship(back_populates="feeds")
    threads: Mapped[list["Thread"]] = relationship(back_populates="feed")
    subscribers: Mapped[list["User"]] = relationship(secondary=feed_subscribers)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50))  # voice, stage
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    position: Mapped[int] = mapped_column(Integer)
    max_members: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    topic: Mapped[Optional[str]] = mapped_column(String(255))
    category: Mapped[Optional["Category"]] = relationship(back_populates="rooms")


class VoiceState(Base):
    __tablename__ = "voice_states"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    self_mute: Mapped[bool] = mapped_column(Boolean, server_default="0")
    self_deaf: Mapped[bool] = mapped_column(Boolean, server_default="0")
    video: Mapped[bool] = mapped_column(Boolean, server_default="0")
    streaming: Mapped[bool] = mapped_column(Boolean, server_default="0")
    server_mute: Mapped[bool] = mapped_column(Boolean, server_default="0")
    server_deaf: Mapped[bool] = mapped_column(Boolean, server_default="0")
    joined_at: Mapped[datetime] = mapped_column(DateTime)


class StageSpeaker(Base):
    __tablename__ = "stage_speakers"

    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("rooms.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime)


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id"), index=True)
    parent_msg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id"))
    archived: Mapped[bool] = mapped_column(Boolean, server_default="0")
    locked: Mapped[bool] = mapped_column(Boolean, server_default="0")

    feed: Mapped["Feed"] = relationship(back_populates="threads")
    subscribers: Mapped[list["User"]] = relationship(secondary=thread_subscribers)


# --- Membership & Permissions ---


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    color: Mapped[Optional[int]] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    permissions: Mapped[int] = mapped_column(BigInteger)  # 64-bit bitfield

    members: Mapped[list["User"]] = relationship(secondary=role_members, back_populates="roles")


class PermissionOverride(Base):
    __tablename__ = "permission_overrides"
    __table_args__ = (
        Index("ix_perm_override_space", "space_type", "space_id"),
        UniqueConstraint("space_type", "space_id", "target_type", "target_id", name="uq_perm_override"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    space_type: Mapped[str] = mapped_column(String(10))  # feed or room
    space_id: Mapped[int] = mapped_column(Integer)
    target_type: Mapped[str] = mapped_column(String(10))  # role or user
    target_id: Mapped[int] = mapped_column(Integer)
    allow: Mapped[int] = mapped_column(BigInteger)
    deny: Mapped[int] = mapped_column(BigInteger)


class Ban(Base):
    __tablename__ = "bans"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Invite(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    feed_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeds.id"))
    max_uses: Mapped[Optional[int]] = mapped_column(Integer)
    uses: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)


# --- DMs ---


class DM(Base):
    __tablename__ = "dms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_group: Mapped[bool] = mapped_column(Boolean, server_default="0")
    name: Mapped[Optional[str]] = mapped_column(String(255))
    icon: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    participants: Mapped[list["User"]] = relationship(secondary=dm_participants)


# --- Messages ---


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # snowflake
    feed_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeds.id"), index=True)
    dm_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dms.id"), index=True)
    thread_id: Mapped[Optional[int]] = mapped_column(ForeignKey("threads.id", use_alter=True), index=True)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[Optional[str]] = mapped_column(Text)
    opaque_blob: Mapped[Optional[str]] = mapped_column(Text)  # E2EE ciphertext
    timestamp: Mapped[int] = mapped_column(BigInteger)  # unix ms
    reply_to: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("messages.id"))
    edit_timestamp: Mapped[Optional[int]] = mapped_column(BigInteger)
    embed: Mapped[Optional[str]] = mapped_column(Text, default=None)
    federated: Mapped[bool] = mapped_column(Boolean, server_default="0")
    author_address: Mapped[Optional[str]] = mapped_column(String(255))
    webhook_id: Mapped[Optional[int]] = mapped_column(ForeignKey("webhooks.id"))

    # Full-text search vector (TSVECTOR on PostgreSQL, TEXT on SQLite — unused on SQLite)
    search_vector = mapped_column(TSVector, nullable=True)

    author: Mapped[Optional["User"]] = relationship()
    attachments: Mapped[list["File"]] = relationship(secondary=message_attachments)


class Reaction(Base):
    __tablename__ = "reactions"

    msg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id"), primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    emoji: Mapped[str] = mapped_column(String(255), primary_key=True)


class Pin(Base):
    __tablename__ = "pins"

    feed_id: Mapped[int] = mapped_column(Integer, ForeignKey("feeds.id"), primary_key=True)
    msg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id"), primary_key=True)
    pinned_at: Mapped[datetime] = mapped_column(DateTime)


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    feed_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeds.id"), nullable=True)
    dm_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dms.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


# --- Read State ---


class FeedReadState(Base):
    __tablename__ = "feed_read_state"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    feed_id: Mapped[int] = mapped_column(Integer, ForeignKey("feeds.id"), primary_key=True)
    last_read_msg_id: Mapped[int] = mapped_column(BigInteger)


class DMReadState(Base):
    __tablename__ = "dm_read_state"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    dm_id: Mapped[int] = mapped_column(Integer, ForeignKey("dms.id"), primary_key=True)
    last_read_msg_id: Mapped[int] = mapped_column(BigInteger)


# --- Social ---


class DMSettings(Base):
    __tablename__ = "dm_settings"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    dm_permission: Mapped[str] = mapped_column(String(50), server_default="everyone")
    # everyone | friends_only | mutual_servers | nobody


# --- E2EE / Devices ---


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Prekey(Base):
    __tablename__ = "prekeys"

    device_id: Mapped[str] = mapped_column(String(255), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    identity_key: Mapped[str] = mapped_column(Text)
    signed_prekey: Mapped[str] = mapped_column(Text)


class OneTimePrekey(Base):
    __tablename__ = "one_time_prekeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(255), ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    key_data: Mapped[str] = mapped_column(Text)


class KeyBackup(Base):
    __tablename__ = "key_backups"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    encrypted_blob: Mapped[str] = mapped_column(Text)


# --- Bots & Webhooks ---


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    avatar: Mapped[Optional[str]] = mapped_column(Text)
    token: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    interaction_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])


class BotCommand(Base):
    __tablename__ = "bot_commands"
    __table_args__ = (UniqueConstraint("bot_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    params: Mapped[Optional[str]] = mapped_column(Text)  # JSON


class Emoji(Base):
    __tablename__ = "emoji"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    image: Mapped[str] = mapped_column(Text)


class Sticker(Base):
    __tablename__ = "stickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    image: Mapped[str] = mapped_column(Text)


# --- Federation ---


class FederationEntry(Base):
    __tablename__ = "federation_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry: Mapped[str] = mapped_column(String(255), unique=True)  # domain or user@domain
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class FederationNonce(Base):
    __tablename__ = "federation_nonces"

    nonce: Mapped[str] = mapped_column(String(255), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class FederationPresenceSub(Base):
    __tablename__ = "federation_presence_subs"
    __table_args__ = (
        UniqueConstraint("user_address", "domain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255))
    user_address: Mapped[str] = mapped_column(String(255), index=True)


# --- Moderation ---


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reported_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    feed_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeds.id"))
    msg_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("messages.id"))
    dm_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dms.id"))
    reason: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    evidence: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String(50), server_default="open", index=True)
    action: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(255), index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    target_id: Mapped[Optional[int]] = mapped_column(Integer)
    extra: Mapped[Optional[str]] = mapped_column("metadata", Text)  # JSON, column named 'metadata'
    timestamp: Mapped[int] = mapped_column(BigInteger)  # unix ms


# --- 2FA ---


class TOTPSecret(Base):
    __tablename__ = "totp_secrets"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    secret: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="0")
    last_used_counter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    credential_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, server_default="0")
    registered_at: Mapped[datetime] = mapped_column(DateTime)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class WebAuthnChallenge(Base):
    __tablename__ = "webauthn_challenges"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    challenge_type: Mapped[str] = mapped_column(String(50))  # registration or authentication
    challenge_data: Mapped[str] = mapped_column(Text)  # JSON
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    used: Mapped[bool] = mapped_column(Boolean, server_default="0")


# --- Event Log (for sync) ---


class StageInvite(Base):
    __tablename__ = "stage_invites"

    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("rooms.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class EventLog(Base):
    __tablename__ = "event_log"
    __table_args__ = (
        Index("ix_event_log_type_ts", "event_type", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # snowflake
    event_type: Mapped[str] = mapped_column(String(255))
    payload: Mapped[str] = mapped_column(Text)  # JSON
    timestamp: Mapped[int] = mapped_column(BigInteger)  # unix ms

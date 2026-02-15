from sqlalchemy import create_mock_engine, MetaData, Table, Column, Integer, String, Boolean, DateTime, \
    ForeignKey, Text, BigInteger, PrimaryKeyConstraint

metadata = MetaData()

# --- Core ---

# User accounts (local and federated)
users_table = Table(
    'users', metadata,
    Column('id', Integer, primary_key=True),
    Column('username', String(255), nullable=False),
    Column('display_name', String(255), nullable=True),
    Column('federated', Boolean, nullable=False),
    Column('active', Boolean, nullable=False, server_default='1'),
    Column('home_domain', String(255), nullable=True),
    Column('created_at', DateTime, nullable=False),
    Column('avatar', Text, nullable=True),  # relative path, base URL in config
    Column('bio', String(255), nullable=True),
    Column('nickname', String(255), nullable=True),
    Column('password_hash', String(255), nullable=True),  # null for federated users
)

# Authenticated sessions, looked up by token
sessions_table = Table(
    'sessions', metadata,
    Column('id', Integer, primary_key=True),
    Column('token', String(255), nullable=False, unique=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('created_at', DateTime, nullable=False),
    Column('expires_at', DateTime, nullable=False),
)

# Key-value server configuration (server name, icon, CDN base URL, etc.)
config_table = Table(
    'config', metadata,
    Column('key', String(255), primary_key=True),
    Column('value', Text, nullable=False),
)

# --- Server Structure ---

# Organizational grouping of feeds and rooms
categories_table = Table(
    'categories', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('position', Integer, nullable=False),
)

# Text channels: text, forum, announcement
feeds_table = Table(
    'feeds', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('type', String(50), nullable=False),  # text, forum, announcement
    Column('topic', String(255), nullable=True),
    Column('category_id', Integer, ForeignKey('categories.id'), nullable=True),  # null = uncategorized
    Column('position', Integer, nullable=False),
)

# Voice/video channels: voice, stage
rooms_table = Table(
    'rooms', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('type', String(50), nullable=False),  # voice, stage
    Column('category_id', Integer, ForeignKey('categories.id'), nullable=True),  # null = uncategorized
    Column('position', Integer, nullable=False),
)

# Sub-conversations branching off a message in a feed
threads_table = Table(
    'threads', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=False),
    Column('parent_msg_id', BigInteger, nullable=False),  # snowflake of the message this thread branches from
    Column('archived', Boolean, nullable=False, server_default='0'),
    Column('locked', Boolean, nullable=False, server_default='0'),
)

# --- Membership & Permissions ---

# Named permission groups with 64-bit bitfield
roles_table = Table(
    'roles', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('color', Integer, nullable=True),  # 24-bit RGB as integer
    Column('position', Integer, nullable=False),
    Column('permissions', BigInteger, nullable=False),  # 64-bit bitfield
)

# Many-to-many: which users have which roles
role_members_table = Table(
    'role_members', metadata,
    Column('role_id', Integer, ForeignKey('roles.id'), nullable=False),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    PrimaryKeyConstraint('role_id', 'user_id'),
)

# Per-feed or per-room permission overrides for a role or user
permission_overrides_table = Table(
    'permission_overrides', metadata,
    Column('id', Integer, primary_key=True),
    Column('space_type', String(10), nullable=False),  # 'feed' or 'room'
    Column('space_id', Integer, nullable=False),  # feed_id or room_id
    Column('target_type', String(10), nullable=False),  # 'role' or 'user'
    Column('target_id', Integer, nullable=False),  # role_id or user_id
    Column('allow', BigInteger, nullable=False),  # permission bits to force ON
    Column('deny', BigInteger, nullable=False),  # permission bits to force OFF
)

# Banned users
ban_table = Table(
    'bans', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('reason', String(255), nullable=True),
    Column('created_at', DateTime, nullable=False),
)

# Server invite codes
invites_table = Table(
    'invites', metadata,
    Column('code', String(50), primary_key=True),
    Column('creator_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=True),
    Column('max_uses', Integer, nullable=True),
    Column('uses', Integer, nullable=False, server_default='0'),
    Column('expires_at', DateTime, nullable=True),
    Column('created_at', DateTime, nullable=False),
)

# --- DMs (defined before messages so dm_id FK works) ---

# Direct message conversations (1:1 and group)
dms_table = Table(
    'dms', metadata,
    Column('id', Integer, primary_key=True),
    Column('is_group', Boolean, nullable=False, server_default='0'),
    Column('name', String(255), nullable=True),  # group DMs only
    Column('icon', Text, nullable=True),  # group DMs only
    Column('created_at', DateTime, nullable=False),
)

# DM membership
dm_participants_table = Table(
    'dm_participants', metadata,
    Column('dm_id', Integer, ForeignKey('dms.id'), nullable=False),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    PrimaryKeyConstraint('dm_id', 'user_id'),
)

# --- Messages ---

# Feed messages and DM messages (snowflake IDs for time-ordering)
messages_table = Table(
    'messages', metadata,
    Column('id', BigInteger, primary_key=True),  # snowflake
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=True),
    Column('dm_id', Integer, ForeignKey('dms.id'), nullable=True),
    Column('thread_id', Integer, nullable=True),
    Column('author_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('body', Text, nullable=True),  # null for E2EE DMs (opaque_blob instead)
    Column('opaque_blob', Text, nullable=True),  # base64 E2EE ciphertext for DMs
    Column('timestamp', BigInteger, nullable=False),  # unix ms
    Column('reply_to', BigInteger, nullable=True),  # snowflake of parent message
    Column('edit_timestamp', BigInteger, nullable=True),
    Column('federated', Boolean, nullable=False, server_default='0'),
    Column('author_address', String(255), nullable=True),  # user@domain for federated
)

# Message reactions (one per user per emoji per message)
reactions_table = Table(
    'reactions', metadata,
    Column('msg_id', BigInteger, ForeignKey('messages.id'), nullable=False),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('emoji', String(255), nullable=False),  # unicode emoji or custom emoji name
    PrimaryKeyConstraint('msg_id', 'user_id', 'emoji'),
)

# Pinned messages in feeds
pins_table = Table(
    'pins', metadata,
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=False),
    Column('msg_id', BigInteger, ForeignKey('messages.id'), nullable=False),
    Column('pinned_at', DateTime, nullable=False),
    PrimaryKeyConstraint('feed_id', 'msg_id'),
)

# Uploaded files/attachments
files_table = Table(
    'files', metadata,
    Column('id', String(255), primary_key=True),  # file_abc123
    Column('name', String(255), nullable=False),
    Column('size', BigInteger, nullable=False),
    Column('mime', String(255), nullable=False),
    Column('url', Text, nullable=False),  # relative path
    Column('uploader_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('created_at', DateTime, nullable=False),
)

# Links messages to their file attachments
message_attachments_table = Table(
    'message_attachments', metadata,
    Column('msg_id', BigInteger, ForeignKey('messages.id'), nullable=False),
    Column('file_id', String(255), ForeignKey('files.id'), nullable=False),
    PrimaryKeyConstraint('msg_id', 'file_id'),
)

# --- Subscriptions ---

# Users subscribed to specific feeds (for notifications)
feed_subscribers_table = Table(
    'feed_subscribers', metadata,
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=False),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    PrimaryKeyConstraint('feed_id', 'user_id'),
)

# Users subscribed to specific threads (for notifications)
thread_subscribers_table = Table(
    'thread_subscribers', metadata,
    Column('thread_id', Integer, ForeignKey('threads.id'), nullable=False),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    PrimaryKeyConstraint('thread_id', 'user_id'),
)

# --- Read State ---

# Last read message per user per feed (for unread indicators)
feed_read_state_table = Table(
    'feed_read_state', metadata,
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=False),
    Column('last_read_msg_id', BigInteger, nullable=False),  # snowflake
    PrimaryKeyConstraint('user_id', 'feed_id'),
)

# Last read message per user per DM (for unread indicators and read receipts)
dm_read_state_table = Table(
    'dm_read_state', metadata,
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('dm_id', Integer, ForeignKey('dms.id'), nullable=False),
    Column('last_read_msg_id', BigInteger, nullable=False),  # snowflake
    PrimaryKeyConstraint('user_id', 'dm_id'),
)

# --- Social ---

# Bidirectional friend relationships
friends_table = Table(
    'friends', metadata,
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('friend_id', Integer, ForeignKey('users.id'), nullable=False),
    PrimaryKeyConstraint('user_id', 'friend_id'),
)

# User blocks
blocks_table = Table(
    'blocks', metadata,
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('blocked_id', Integer, ForeignKey('users.id'), nullable=False),
    PrimaryKeyConstraint('user_id', 'blocked_id'),
)

# Per-user DM privacy settings
dm_settings_table = Table(
    'dm_settings', metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('dm_permission', String(50), nullable=False, server_default='everyone'),
    # everyone | friends_only | mutual_servers | nobody
)

# --- E2EE / Devices ---

# User devices for MLS encryption
devices_table = Table(
    'devices', metadata,
    Column('id', String(255), primary_key=True),  # dev_abc123
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('device_name', String(255), nullable=False),
    Column('created_at', DateTime, nullable=False),
)

# Long-lived identity and signed prekeys (one set per device)
prekeys_table = Table(
    'prekeys', metadata,
    Column('device_id', String(255), ForeignKey('devices.id'), primary_key=True),
    Column('identity_key', Text, nullable=False),  # base64
    Column('signed_prekey', Text, nullable=False),  # base64
)

# Consumable one-time prekeys (many per device, deleted after use)
one_time_prekeys_table = Table(
    'one_time_prekeys', metadata,
    Column('id', Integer, primary_key=True),
    Column('device_id', String(255), ForeignKey('devices.id'), nullable=False),
    Column('key_data', Text, nullable=False),  # base64
)

# Encrypted E2EE key backup (one per user, decrypted with recovery passphrase)
key_backups_table = Table(
    'key_backups', metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('encrypted_blob', Text, nullable=False),  # base64
)

# --- Bots & Webhooks ---

# Feed webhooks for external integrations (CI/CD, notifications)
webhooks_table = Table(
    'webhooks', metadata,
    Column('id', Integer, primary_key=True),
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=False),
    Column('name', String(255), nullable=False),
    Column('avatar', Text, nullable=True),
    Column('token', String(255), nullable=False, unique=True),
    Column('created_at', DateTime, nullable=False),
)

# Bot configuration (linked to a user account and an owner)
bots_table = Table(
    'bots', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False, unique=True),  # the bot's user account
    Column('owner_id', Integer, ForeignKey('users.id'), nullable=False),  # who owns/created the bot
    Column('interaction_url', Text, nullable=True),  # callback URL for HTTP-only bots
    Column('created_at', DateTime, nullable=False),
)

# Registered slash commands for bots
bot_commands_table = Table(
    'bot_commands', metadata,
    Column('id', Integer, primary_key=True),
    Column('bot_id', Integer, ForeignKey('bots.id'), nullable=False),
    Column('name', String(255), nullable=False),
    Column('description', String(255), nullable=True),
    Column('params', Text, nullable=True),  # JSON array of param definitions
)

# Custom server emoji
emoji_table = Table(
    'emoji', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False, unique=True),
    Column('creator_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('image', Text, nullable=False),  # relative path
)

# Custom server stickers
stickers_table = Table(
    'stickers', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False, unique=True),
    Column('creator_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('image', Text, nullable=False),  # relative path
)

# --- Federation ---

# Federation list entries (whitelist or blacklist, controlled by config 'federation_mode')
# Supports both full domains and specific user@domain addresses
federation_list_table = Table(
    'federation_list', metadata,
    Column('id', Integer, primary_key=True),
    Column('entry', String(255), nullable=False, unique=True),  # domain or user@domain
    Column('reason', String(255), nullable=True),
    Column('created_at', DateTime, nullable=False),
)

# --- Moderation ---

# User-submitted abuse reports (includes decrypted DM excerpts)
reports_table = Table(
    'reports', metadata,
    Column('id', Integer, primary_key=True),
    Column('reporter_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('reported_user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('feed_id', Integer, ForeignKey('feeds.id'), nullable=True),
    Column('msg_id', BigInteger, ForeignKey('messages.id'), nullable=True),
    Column('dm_id', Integer, ForeignKey('dms.id'), nullable=True),
    Column('reason', String(50), nullable=False),  # harassment, spam, illegal_content, threats, other
    Column('description', Text, nullable=True),
    Column('evidence', Text, nullable=True),  # JSON array of decrypted message excerpts
    Column('status', String(50), nullable=False, server_default='open'),  # open, resolved
    Column('action', String(50), nullable=True),  # dismiss, warn, kick, ban
    Column('created_at', DateTime, nullable=False),
)

# Immutable audit trail of administrative actions
audit_log_table = Table(
    'audit_log', metadata,
    Column('id', BigInteger, primary_key=True),
    Column('event_type', String(255), nullable=False),  # dot-notation: member.kick, role.assign, etc.
    Column('actor_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('target_id', Integer, nullable=True),
    Column('metadata', Text, nullable=True),  # JSON
    Column('timestamp', BigInteger, nullable=False),  # unix ms
)

# --- 2FA ---

# TOTP (time-based one-time password) secrets
totp_secrets_table = Table(
    'totp_secrets', metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('secret', String(255), nullable=False),
    Column('enabled', Boolean, nullable=False, server_default='0'),
)

# WebAuthn/FIDO2 credentials (hardware keys, biometrics)
webauthn_credentials_table = Table(
    'webauthn_credentials', metadata,
    Column('credential_id', String(255), primary_key=True),  # base64
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('name', String(255), nullable=False),
    Column('public_key', Text, nullable=False),  # base64
    Column('registered_at', DateTime, nullable=False),
    Column('last_used_at', DateTime, nullable=True),
)

# Single-use recovery codes (hashed, 8 per user)
recovery_codes_table = Table(
    'recovery_codes', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('code_hash', String(255), nullable=False),  # bcrypt or argon2
    Column('used', Boolean, nullable=False, server_default='0'),
)

# --- DDL Generation ---

def dump(sql, *multiparams, **params):
    print(sql.compile(dialect=engine.dialect))

engine = create_mock_engine('postgresql://', dump)
metadata.create_all(engine, checkfirst=False)

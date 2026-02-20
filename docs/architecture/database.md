# Database Schema Reference

This page documents all database tables in the Vox server, organised by
functional category.

---

## Core

### users

Primary user account table.

| Column | Type | Notes |
|---|---|---|
| id | uint32 PK | Auto-increment entity ID |
| username | text | Unique, login identifier |
| display_name | text | Shown in UI |
| federated | boolean | Whether this is a federated (remote) user |
| active | boolean | Account enabled flag |
| home_domain | text | Origin domain for federated users |
| created_at | timestamp | Account creation time |
| avatar | text | Avatar URL or file reference |
| bio | text | Profile biography |
| nickname | text | Server-scoped display override |
| password_hash | text | Argon2 / bcrypt hash |

### sessions

Active login sessions.

| Column | Type | Notes |
|---|---|---|
| id | PK | Session identifier |
| user_id | FK -> users | Owning user |
| token | text | Bearer token |
| created_at | timestamp | |
| expires_at | timestamp | |

### config

Server-wide configuration key-value store.

| Column | Type | Notes |
|---|---|---|
| key | text PK | Configuration key |
| value | text | Configuration value |

---

## Server Structure

### categories

Organisational grouping for feeds and rooms.

| Column | Type | Notes |
|---|---|---|
| id | uint32 PK | |
| name | text | Display name |
| position | integer | Sort order |

### feeds

Text-based channels.

| Column | Type | Notes |
|---|---|---|
| id | uint32 PK | Entity ID (separate ID space from DMs) |
| category_id | FK -> categories | Parent category |
| name | text | Channel name |
| type | enum | `text`, `forum`, `announcement` |
| position | integer | Sort order within category |

### rooms

Voice / video channels.

| Column | Type | Notes |
|---|---|---|
| id | uint32 PK | |
| category_id | FK -> categories | Parent category |
| name | text | Channel name |
| type | enum | `voice`, `stage` |
| position | integer | Sort order within category |

### threads

Threaded conversations inside feeds.

| Column | Type | Notes |
|---|---|---|
| id | uint32 PK | Scoped to parent feed |
| feed_id | FK -> feeds | Parent feed |
| title | text | Thread title |
| created_at | timestamp | |
| archived | boolean | |

---

## Membership & Permissions

### roles

Permission roles.

| Column | Type | Notes |
|---|---|---|
| id | uint32 PK | |
| name | text | Role name |
| permissions | uint64 | 64-bit permission bitfield |
| colour | integer | Display colour |
| position | integer | Hierarchy position (higher = more authority) |

### role_members

Many-to-many join between users and roles.

| Column | Type | Notes |
|---|---|---|
| role_id | FK -> roles | |
| user_id | FK -> users | |

### permission_overrides

Feed / room-level permission overrides.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| feed_id | FK -> feeds | Nullable (set for feed overrides) |
| room_id | FK -> rooms | Nullable (set for room overrides) |
| target_type | enum | `role`, `user` |
| target_id | uint32 | Role ID or user ID |
| allow | uint64 | Bits to grant |
| deny | uint64 | Bits to revoke |

### bans

Server bans.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| user_id | FK -> users | Banned user |
| reason | text | |
| banned_at | timestamp | |

### invites

Invite links.

| Column | Type | Notes |
|---|---|---|
| code | text PK | Unique invite code |
| creator_id | FK -> users | |
| uses | integer | Current use count |
| max_uses | integer | Nullable; unlimited if null |
| expires_at | timestamp | Nullable |

---

## Messages

### messages

All messages, in feeds, DMs, and threads.

| Column | Type | Notes |
|---|---|---|
| id | uint64 PK | Snowflake ID |
| author_id | FK -> users | |
| feed_id | FK -> feeds | Nullable (set for feed/thread messages) |
| dm_id | FK -> dms | Nullable (set for DM messages) |
| thread_id | FK -> threads | Nullable (set for thread messages) |
| body | text | Plaintext or Markdown body (null when E2EE) |
| opaque_blob | blob | Encrypted message payload for E2EE |
| created_at | timestamp | Derived from Snowflake, but stored for indexing |
| edited_at | timestamp | Nullable |

### reactions

Emoji reactions on messages.

| Column | Type | Notes |
|---|---|---|
| message_id | FK -> messages | |
| user_id | FK -> users | |
| emoji | text | Unicode emoji or custom emoji ID |

### pins

Pinned messages.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| feed_id | FK -> feeds | |
| message_id | FK -> messages | |
| pinned_by | FK -> users | |
| pinned_at | timestamp | |

### files

Uploaded file metadata.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| uploader_id | FK -> users | |
| filename | text | Original file name |
| content_type | text | MIME type |
| size | integer | Bytes |
| url | text | Storage URL |
| uploaded_at | timestamp | |

### message_attachments

Join table linking messages to files.

| Column | Type | Notes |
|---|---|---|
| message_id | FK -> messages | |
| file_id | FK -> files | |

---

## Direct Messages

### dms

DM conversation containers.

| Column | Type | Notes |
|---|---|---|
| id | uint32 PK | Separate ID space from feeds |
| created_at | timestamp | |

### dm_participants

Members of a DM conversation (supports group DMs).

| Column | Type | Notes |
|---|---|---|
| dm_id | FK -> dms | |
| user_id | FK -> users | |

### dm_settings

Per-user settings for a DM (mute, notification level).

| Column | Type | Notes |
|---|---|---|
| dm_id | FK -> dms | |
| user_id | FK -> users | |
| muted | boolean | |

### dm_read_state

Tracks the last-read message in each DM.

| Column | Type | Notes |
|---|---|---|
| dm_id | FK -> dms | |
| user_id | FK -> users | |
| last_read_id | uint64 | Snowflake of last read message |

### feed_read_state

Tracks the last-read message in each feed.

| Column | Type | Notes |
|---|---|---|
| feed_id | FK -> feeds | |
| user_id | FK -> users | |
| last_read_id | uint64 | Snowflake of last read message |

---

## Social

### friends

Friend relationships.

| Column | Type | Notes |
|---|---|---|
| user_id | FK -> users | |
| friend_id | FK -> users | |
| status | enum | `pending`, `accepted` |
| created_at | timestamp | |

### blocks

User blocks.

| Column | Type | Notes |
|---|---|---|
| user_id | FK -> users | Blocking user |
| blocked_id | FK -> users | Blocked user |

---

## End-to-End Encryption

### devices

Registered client devices for E2EE key distribution.

| Column | Type | Notes |
|---|---|---|
| id | PK | Device ID |
| user_id | FK -> users | |
| identity_key | blob | Long-term identity public key |
| created_at | timestamp | |

### prekeys

Signed pre-keys for key agreement.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| device_id | FK -> devices | |
| public_key | blob | |
| signature | blob | |

### one_time_prekeys

Ephemeral one-time pre-keys (consumed on use).

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| device_id | FK -> devices | |
| public_key | blob | |

### key_backups

Encrypted key backup blobs.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| user_id | FK -> users | |
| data | blob | Encrypted backup |
| created_at | timestamp | |

---

## Bots & Webhooks

### webhooks

Incoming webhooks for external integrations.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| feed_id | FK -> feeds | Target feed |
| name | text | |
| token | text | Webhook secret |
| creator_id | FK -> users | |

### bots

Bot application accounts.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| owner_id | FK -> users | |
| name | text | |
| token | text | Bot authentication token |

### bot_commands

Registered slash commands for bots.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| bot_id | FK -> bots | |
| name | text | Command name |
| description | text | |

---

## Moderation

### reports

User-submitted reports.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| reporter_id | FK -> users | |
| target_id | FK -> users | Reported user |
| message_id | FK -> messages | Nullable; reported message |
| reason | text | |
| created_at | timestamp | |

### audit_log

Immutable log of administrative actions.

| Column | Type | Notes |
|---|---|---|
| id | uint64 PK | Snowflake ID |
| actor_id | FK -> users | Who performed the action |
| action | text | Action type identifier |
| target_type | text | Entity type affected |
| target_id | uint32 | Entity ID affected |
| details | json | Additional context |
| created_at | timestamp | |

---

## Two-Factor Authentication

### totp_secrets

TOTP (time-based one-time password) secrets.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| user_id | FK -> users | |
| secret | text | Base32-encoded TOTP secret |
| verified | boolean | Whether initial verification passed |

### webauthn_credentials

Registered WebAuthn / passkey credentials.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| user_id | FK -> users | |
| credential_id | blob | WebAuthn credential ID |
| public_key | blob | |
| sign_count | integer | |

### recovery_codes

Backup recovery codes for 2FA bypass.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| user_id | FK -> users | |
| code_hash | text | Hashed recovery code |
| used | boolean | |

---

## Federation

### federation_list

Known federated servers.

| Column | Type | Notes |
|---|---|---|
| domain | text PK | Remote server domain |
| status | enum | `allowed`, `blocked` |
| public_key | blob | Remote server's signing key |

---

## Emoji & Stickers

### emoji

Custom server emoji.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| name | text | Emoji shortcode |
| url | text | Image URL |
| creator_id | FK -> users | |

### stickers

Custom server stickers.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| name | text | |
| url | text | Image URL |
| creator_id | FK -> users | |

---

## Subscriptions

### feed_subscribers

Users subscribed to notifications for a feed.

| Column | Type | Notes |
|---|---|---|
| feed_id | FK -> feeds | |
| user_id | FK -> users | |

### thread_subscribers

Users subscribed to notifications for a thread.

| Column | Type | Notes |
|---|---|---|
| thread_id | FK -> threads | |
| feed_id | FK -> feeds | Parent feed (for thread scoping) |
| user_id | FK -> users | |

---

## Entity Relationship Overview

```
users ---< sessions
users ---< role_members >--- roles
users ---< devices ---< prekeys
                   ---< one_time_prekeys
users ---< key_backups
users ---< friends
users ---< blocks
users ---< bots ---< bot_commands
users ---< webhooks
users ---< reports
users ---< totp_secrets
users ---< webauthn_credentials
users ---< recovery_codes

categories ---< feeds ---< threads
           ---< rooms

feeds ---< messages ---< reactions
                   ---< message_attachments >--- files
                   ---< pins
feeds ---< permission_overrides
feeds ---< feed_read_state
feeds ---< feed_subscribers

rooms ---< permission_overrides

dms ---< dm_participants >--- users
dms ---< dm_settings
dms ---< dm_read_state
dms ---< messages

threads ---< messages
threads ---< thread_subscribers
```

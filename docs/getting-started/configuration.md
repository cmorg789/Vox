---
title: Configuration
description: Full reference for Vox's three-tier configuration system.
---

# Configuration

Vox uses a three-tier configuration system. Settings are resolved in the following priority order:

```
Environment Variables  >  DB Config Table  >  Field Defaults
```

1. **Environment variables** -- Highest priority. Prefixed with `VOX_` and grouped by section.
2. **DB Config table** -- Key-value pairs stored in the database. Editable at runtime via the admin API.
3. **Field defaults** -- Hard-coded fallback values defined in the application.

!!! info "Runtime updates"
    Settings stored in the DB Config table can be changed at runtime through the admin API without restarting the server. Environment variable overrides always take precedence.

---

## Config Sections

### Server Identity (`VOX_SERVER_` prefix)

Server-level metadata and connectivity settings.

| Environment Variable | Config Key | Type | Default | Description |
|---|---|---|---|---|
| `VOX_SERVER_NAME` | `server.name` | `str` | `"Vox"` | Display name of the server |
| `VOX_SERVER_ICON` | `server.icon` | `str` | `null` | URL to the server icon |
| `VOX_SERVER_DESCRIPTION` | `server.description` | `str` | `""` | Short server description |
| `VOX_SERVER_GATEWAY_URL` | `server.gateway_url` | `str` | `null` | Public WebSocket gateway URL for clients to connect to |

### Auth (`VOX_AUTH_` prefix)

Authentication and session settings.

| Environment Variable | Config Key | Type | Default | Description |
|---|---|---|---|---|
| `VOX_AUTH_SESSION_TTL_DAYS` | `auth.session_ttl_days` | `int` | `30` | Number of days before a session token expires |

### Limits (`VOX_LIMIT_` prefix)

Rate limits, size limits, and pagination constraints.

| Environment Variable | Config Key | Type | Default | Description |
|---|---|---|---|---|
| `VOX_LIMIT_MESSAGE_BODY_MAX` | `limits.message_body_max` | `int` | `4000` | Maximum message body length in characters |
| `VOX_LIMIT_FILE_UPLOAD_MAX_BYTES` | `limits.file_upload_max_bytes` | `int` | `26214400` | Maximum file upload size in bytes (default 25 MB) |
| `VOX_LIMIT_GROUP_DM_RECIPIENTS_MAX` | `limits.group_dm_recipients_max` | `int` | `10` | Maximum number of recipients in a group DM |
| `VOX_LIMIT_MAX_DEVICES` | `limits.max_devices` | `int` | `10` | Maximum number of devices per user |
| `VOX_LIMIT_PAGE_SIZE_DEFAULT` | `limits.page_size_default` | `int` | `50` | Default page size for paginated endpoints |
| `VOX_LIMIT_PAGE_SIZE_MAX` | `limits.page_size_max` | `int` | `100` | Maximum allowed page size |
| `VOX_LIMIT_MAX_PINS_PER_FEED` | `limits.max_pins_per_feed` | `int` | `50` | Maximum number of pinned messages per feed |
| `VOX_LIMIT_FEDERATION_PRESENCE_SUB_LIMIT` | `limits.federation_presence_sub_limit` | `int` | `1000` | Maximum presence subscriptions per federated domain |

### Media (`VOX_MEDIA_` prefix)

Media server and file handling configuration.

| Environment Variable | Config Key | Type | Default | Description |
|---|---|---|---|---|
| `VOX_MEDIA_URL` | `media.url` | `str` | `null` | Public URL for the media/SFU endpoint |
| `VOX_MEDIA_TLS_CERT` | `media.tls_cert` | `str` | `null` | Path to TLS certificate for QUIC transport |
| `VOX_MEDIA_TLS_KEY` | `media.tls_key` | `str` | `null` | Path to TLS private key for QUIC transport |
| `VOX_MEDIA_ALLOWED_FILE_MIMES` | `media.allowed_file_mimes` | `list` | `[]` | List of allowed MIME types for file uploads. Empty list allows all types. |

### WebAuthn (`VOX_WEBAUTHN_` prefix)

WebAuthn/passkey authentication settings.

| Environment Variable | Config Key | Type | Default | Description |
|---|---|---|---|---|
| `VOX_WEBAUTHN_RP_ID` | `webauthn.rp_id` | `str` | `null` | Relying Party ID (typically your domain name, e.g. `example.com`) |
| `VOX_WEBAUTHN_ORIGIN` | `webauthn.origin` | `str` | `null` | Expected origin for WebAuthn ceremonies (e.g. `https://example.com`) |

!!! info "Optional configuration"
    Both `rp_id` and `origin` must be set for WebAuthn registration and authentication to work. These should match your deployment domain. If left unset, WebAuthn endpoints return `400 WEBAUTHN_NOT_CONFIGURED`.

### Federation (`VOX_FEDERATION_` prefix)

Federation settings for cross-server communication.

| Environment Variable | Config Key | Type | Default | Description |
|---|---|---|---|---|
| `VOX_FEDERATION_DOMAIN` | `federation.domain` | `str` | `null` | The domain name this server is authoritative for |
| `VOX_FEDERATION_POLICY` | `federation.policy` | `str` | `"closed"` | Federation policy: `open`, `allow_list`, or `closed` |
| `VOX_FEDERATION_PRIVATE_KEY` | `federation.private_key` | `str` | `null` | Path to the Ed25519 private key used to sign outgoing federation requests |
| `VOX_FEDERATION_PUBLIC_KEY` | `federation.public_key` | `str` | `null` | Path to the Ed25519 public key published for other servers to verify requests |

!!! note "Federation policies"
    - **`closed`** -- No federation. The server operates in isolation (default).
    - **`allow_list`** -- Only federate with explicitly approved servers.
    - **`open`** -- Federate with any server that initiates contact.

### Database (`VOX_DB_` prefix)

Database connection settings. Pool settings apply to PostgreSQL only; SQLite uses a single connection with WAL mode enabled automatically.

| Environment Variable | Type | Default | Description |
|---|---|---|---|
| `VOX_DB_POOL_SIZE` | `int` | `10` | PostgreSQL connection pool size |
| `VOX_DB_MAX_OVERFLOW` | `int` | `20` | Maximum overflow connections above pool size |
| `VOX_DB_POOL_RECYCLE` | `int` | `1800` | Seconds before a connection is recycled |

!!! note "SQLite defaults"
    When using SQLite, the engine automatically enables WAL mode (`journal_mode=WAL`), sets `synchronous=NORMAL`, and configures a 5-second busy timeout. These are not configurable via environment variables.

### Logging (`VOX_LOG_` prefix)

| Environment Variable | Type | Default | Description |
|---|---|---|---|
| `VOX_LOG_FORMAT` | `str` | `"json"` | Log output format. `"json"` for structured JSON logging, any other value for plain text. |

---

## DB Config Table

Configuration values can be stored in the database using the `Config` model. Each row is a key-value pair:

| Column | Type | Description |
|---|---|---|
| `key` | `str` | Dot-separated config key (e.g. `server.name`) |
| `value` | `str` | The configuration value (stored as a string, parsed by the application) |

### Admin API

Administrators can read and update configuration at runtime through the admin API:

```bash
# Get current config
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/admin/config

# Update a config value
curl -X PUT \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"key": "server.name", "value": "My Community"}' \
     http://localhost:8000/api/admin/config
```

!!! tip "Environment overrides"
    If an environment variable is set for a config key, the DB value for that key is ignored. Remove the environment variable to allow the DB value to take effect.

---

## Example Environment File

A typical `.env` file for a production deployment:

```bash
# Server identity
VOX_SERVER_NAME="My Community"
VOX_SERVER_DESCRIPTION="A place to hang out"
VOX_SERVER_GATEWAY_URL="wss://chat.example.com/gateway"

# Auth
VOX_AUTH_SESSION_TTL_DAYS=14

# Limits
VOX_LIMIT_MESSAGE_BODY_MAX=4000
VOX_LIMIT_FILE_UPLOAD_MAX_BYTES=52428800
VOX_LIMIT_MAX_PINS_PER_FEED=50

# Database (PostgreSQL)
VOX_DB_POOL_SIZE=10
VOX_DB_MAX_OVERFLOW=20
VOX_DB_POOL_RECYCLE=1800

# Logging
VOX_LOG_FORMAT=json

# Media (QUIC SFU)
VOX_MEDIA_URL="https://media.example.com"
VOX_MEDIA_TLS_CERT="/etc/vox/cert.pem"
VOX_MEDIA_TLS_KEY="/etc/vox/key.pem"

# WebAuthn
VOX_WEBAUTHN_RP_ID="example.com"
VOX_WEBAUTHN_ORIGIN="https://chat.example.com"

# Federation
VOX_FEDERATION_DOMAIN="example.com"
VOX_FEDERATION_POLICY="open"
VOX_FEDERATION_PRIVATE_KEY="/etc/vox/federation.key"
VOX_FEDERATION_PUBLIC_KEY="/etc/vox/federation.pub"
```

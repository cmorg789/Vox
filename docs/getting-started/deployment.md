---
title: Deployment
description: Deploy Vox behind a reverse proxy with TLS termination.
---

# Deployment

This guide covers deploying Vox behind a reverse proxy with TLS. Vox itself listens on plain HTTP; a reverse proxy handles HTTPS, certificate management, and WebSocket upgrades.

## Architecture

```
Clients ──▶ Reverse Proxy (TLS) ──▶ Vox (HTTP :8000)
               ├─ HTTPS  /api/v1/*
               ├─ WSS    /gateway
               └─ HTTPS  /health, /ready
```

Vox serves three types of traffic on a single port:

| Path | Protocol | Purpose |
|---|---|---|
| `/api/v1/*` | HTTP | REST API |
| `/gateway` | WebSocket | Real-time event gateway |
| `/health`, `/ready` | HTTP | Health and readiness probes |

---

## Reverse Proxy Configuration

### Caddy

Caddy is the simplest option — it handles TLS certificates automatically via Let's Encrypt.

```caddy title="Caddyfile"
chat.example.com {
    reverse_proxy localhost:8000
}
```

That's it. Caddy automatically:

- Obtains and renews TLS certificates
- Upgrades WebSocket connections (no special config needed)
- Sets `X-Forwarded-For` and related headers
- Serves HTTP/2

For more control:

```caddy title="Caddyfile"
chat.example.com {
    # Increase timeouts for long-lived WebSocket connections
    reverse_proxy localhost:8000 {
        transport http {
            read_timeout 0
        }
    }

    # Optional: serve a static frontend
    handle /app/* {
        root * /var/www/vox-client
        file_server
    }

    # Compression for API responses
    encode gzip zstd
}
```

### Nginx

```nginx title="/etc/nginx/sites-available/vox"
upstream vox {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name chat.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name chat.example.com;

    ssl_certificate     /etc/letsencrypt/live/chat.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chat.example.com/privkey.pem;

    # --- WebSocket gateway ---
    location /gateway {
        proxy_pass http://vox;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable buffering for real-time events
        proxy_buffering off;

        # Keep WebSocket connections alive
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # --- REST API and health endpoints ---
    location / {
        proxy_pass http://vox;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Allow large file uploads (matches VOX_LIMIT_FILE_UPLOAD_MAX_BYTES)
        client_max_body_size 25m;
    }
}
```

Obtain certificates with certbot:

```bash
sudo certbot --nginx -d chat.example.com
```

---

## Vox Configuration for Proxied Deployments

Set these environment variables so Vox knows its public-facing URLs:

```bash
# The public gateway URL clients will connect to
VOX_SERVER_GATEWAY_URL="wss://chat.example.com/gateway"

# WebAuthn must match the public domain
VOX_WEBAUTHN_RP_ID="chat.example.com"
VOX_WEBAUTHN_ORIGIN="https://chat.example.com"

# Federation domain (if enabled)
VOX_FEDERATION_DOMAIN="chat.example.com"
```

!!! warning "Gateway URL is required"
    Clients discover the WebSocket endpoint from `VOX_SERVER_GATEWAY_URL`. If this is not set or points to the wrong host, real-time features will not work.

---

## Running Vox

### systemd

Create a service file to run Vox as a daemon:

```ini title="/etc/systemd/system/vox.service"
[Unit]
Description=Vox Chat Server
After=network.target postgresql.service

[Service]
Type=exec
User=vox
WorkingDirectory=/opt/vox
EnvironmentFile=/opt/vox/.env
ExecStart=/opt/vox/.venv/bin/uvicorn vox.api.app:create_app \
    --factory \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now vox
```

!!! warning "Single worker"
    Vox uses in-process state for the gateway hub, rate limiter, and presence. Always run with `--workers 1`.

### Docker

A minimal Dockerfile:

```dockerfile title="Dockerfile"
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Rust (needed for vox-sfu)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "vox.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

```yaml title="docker-compose.yml"
services:
  vox:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      VOX_DATABASE_URL: "postgresql+asyncpg://vox:secret@db:5432/vox"
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: vox
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: vox
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vox"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

---

## Health Checks

Use the built-in endpoints for load balancer or orchestrator health checks:

| Endpoint | Purpose | Failure |
|---|---|---|
| `GET /health` | Liveness — process is running | Never fails (if reachable, it's alive) |
| `GET /ready` | Readiness — database is connected | Returns 503 if the database is unreachable |

Example health check configuration for a load balancer:

```
Health check path:    /ready
Interval:             10s
Healthy threshold:    2
Unhealthy threshold:  3
```

---

## Production Checklist

- [ ] Reverse proxy with TLS termination (Caddy or Nginx + certbot)
- [ ] `VOX_SERVER_GATEWAY_URL` set to the public `wss://` URL
- [ ] `VOX_DATABASE_URL` pointing to PostgreSQL (not SQLite)
- [ ] Database migrations applied: `alembic upgrade head`
- [ ] `VOX_WEBAUTHN_RP_ID` and `VOX_WEBAUTHN_ORIGIN` set if using passkeys
- [ ] File storage configured (local path or S3)
- [ ] `VOX_LOG_FORMAT=json` for structured logging
- [ ] systemd service or container with restart policy
- [ ] Single worker process (`--workers 1`)
- [ ] `client_max_body_size` (Nginx) matches `VOX_LIMIT_FILE_UPLOAD_MAX_BYTES`

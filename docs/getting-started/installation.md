---
title: Installation
description: Install Vox and its dependencies from source.
---

# Installation

## Prerequisites

### Python 3.11+

Vox requires Python 3.11 or later. Verify your version:

```bash
python3 --version
```

### Rust Toolchain

The `vox-sfu` media component is written in Rust and compiled as a Python extension using [maturin](https://www.maturin.rs/). Install Rust via [rustup](https://rustup.rs/):

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

## Install from Source

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/vox.git
cd vox
```

### 2. Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Vox

Install the server and all its dependencies:

```bash
pip install -e .
```

This installs the core dependencies:

| Package | Purpose |
|---|---|
| FastAPI >=0.115 | HTTP framework |
| SQLAlchemy[asyncio] >=2.0 | Async ORM and database toolkit |
| aiosqlite >=0.20 | Async SQLite driver |
| websockets >=13.0 | WebSocket gateway |
| pydantic >=2.0 | Data validation and serialization |
| argon2-cffi | Password hashing |
| pyjwt | JWT session tokens |
| cryptography | Cryptographic operations |
| pyotp | TOTP two-factor authentication |
| webauthn | WebAuthn/passkey authentication |
| vox-sfu | QUIC-based media SFU |
| zstandard | Zstd compression |
| dnspython | DNS lookups for federation |

!!! note "Rust SFU"
    The `vox-sfu` media component is a Rust Python extension and is listed as a dependency in `pyproject.toml`. It will be compiled automatically during install if a Rust toolchain is available. Make sure you have Rust installed **before** running `pip install`.

### 4. Install Dev Dependencies (Optional)

For development and testing:

```bash
pip install -e ".[dev]"
```

This adds:

| Package | Purpose |
|---|---|
| pytest | Test runner |
| pytest-asyncio | Async test support |
| httpx | Async HTTP client for testing |
| ruff | Linter and formatter |
| maturin | Rust-Python build tool |

## Running the Server

### Using the CLI

Vox provides a CLI entry point:

```bash
vox
```

### Using Uvicorn Directly

For more control over the server process:

```bash
uvicorn vox.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

!!! note "Factory pattern"
    The `--factory` flag is required because `create_app` is an application factory function, not a pre-built ASGI app instance.

### Common Uvicorn Options

```bash
uvicorn vox.api.app:create_app --factory \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
```

!!! warning "Single worker"
    Vox uses in-process state for the WebSocket gateway. Run with a single worker (`--workers 1`) unless you have configured an external message broker.

## Verifying the Installation

Once the server is running, check that it responds:

```bash
curl http://localhost:8000/
```

You should receive a JSON response with server information.

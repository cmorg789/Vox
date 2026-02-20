# Environment Setup

## Prerequisites

- **Python 3.11+** -- Required for the server and SDK.
- **Rust toolchain** -- Required for building `vox-sfu` and `vox-media`. Install via [rustup](https://rustup.rs/).
- **Git** -- For cloning the repository.

## Clone and install

```bash
git clone <repo-url>
cd Vox
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the Vox server and all development dependencies (pytest, ruff, etc.) in editable mode.

## Build Rust extensions

The SFU (Selective Forwarding Unit) and media codec bindings are written in Rust and built with maturin.

### Build the SFU

```bash
cd crates/vox-sfu
maturin develop
```

### Build media bindings (optional)

```bash
cd crates/vox-media
maturin develop
```

## Run the server

With the virtualenv active:

```bash
vox
```

Or using uvicorn directly with auto-reload for development:

```bash
uvicorn vox.api.app:create_app --factory --reload
```

The server starts on `http://127.0.0.1:8000` by default.

## Project structure

```
Vox/
  src/vox/           Server application
    api/             FastAPI routes and WebSocket gateway
    db/              SQLAlchemy models and database setup
  sdk/               Python client SDK (vox-sdk)
  crates/            Rust extensions
    vox-sfu/         Selective Forwarding Unit (voice/video)
    vox-media/       AV1 codec bindings
  tests/             Server test suite
  docs/              MkDocs documentation
```

## Code style

The project uses **ruff** for both linting and formatting.

- Line length: **100** characters.
- Target: **Python 3.11**.

Run the linter:

```bash
ruff check .
```

Auto-format:

```bash
ruff format .
```

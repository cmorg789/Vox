# Development Guide

This section covers everything you need to contribute to the Vox project, from setting up your environment to running the test suite.

## Contents

- [Environment setup](setup.md) -- Install prerequisites, clone the repo, and run the server locally.
- [Testing](testing.md) -- Run the test suite, understand test organization, and write new tests.

## Architecture overview

Vox is composed of several components:

- **`src/vox/`** -- The main server application, built with Python, FastAPI, and SQLAlchemy async.
- **`sdk/`** -- The Python client SDK (`vox-sdk`) for interacting with the Vox API and gateway.
- **`crates/`** -- Rust extensions including `vox-sfu` (Selective Forwarding Unit for voice/video) and `vox-media` (AV1 codec bindings).
- **`tests/`** -- Server test suite using pytest and pytest-asyncio.
- **`docs/`** -- This documentation site, built with MkDocs Material.

## Quick links

- [SDK documentation](../sdk/index.md)
- [Error code reference](../reference/errors.md)
- [Rate limit reference](../reference/rate-limits.md)

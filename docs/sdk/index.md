# Vox SDK

The **vox-sdk** package is an async Python client for the Vox Protocol. It provides a complete interface for interacting with Vox servers, including both the HTTP REST API and the real-time WebSocket gateway.

## Features

- **Full API coverage** -- Access all 19 API groups (auth, messages, channels, members, roles, server, users, invites, voice, DMs, webhooks, bots, E2EE, moderation, files, federation, search, emoji, sync, and embeds) through a single client instance.
- **WebSocket gateway client** -- Real-time event streaming with automatic reconnection, session resumption, and exponential backoff with jitter.
- **Pydantic response models** -- All API responses are deserialized into typed Pydantic v2 models for autocompletion and validation.
- **Rate limit awareness** -- Automatic tracking of rate limit headers with built-in retry on 429 responses, respecting the server's `retry_after_ms` value.
- **Zstandard compression** -- Optional zstd compression for gateway messages (server-to-client), reducing bandwidth for high-throughput connections.
- **Async context manager pattern** -- Clean resource management with `async with` for both the HTTP client and gateway connections.

## Requirements

- Python >= 3.11
- [httpx](https://www.python-httpx.org/) >= 0.27
- [websockets](https://websockets.readthedocs.io/) >= 13.0
- [pydantic](https://docs.pydantic.dev/) >= 2.0
- [zstandard](https://github.com/indygreg/python-zstandard) >= 0.23

### Optional dependencies

- **maturin** -- Required for building the Rust-based `vox-media` codec bindings, which provide AV1 encode/decode and camera capture support.

## Getting started

See the [Quickstart guide](quickstart.md) to install the SDK and start building with Vox.

## Reference

- [HTTP Client reference](client.md)
- [Gateway Client reference](gateway-client.md)
- [Error codes](../reference/errors.md)
- [Rate limits](../reference/rate-limits.md)

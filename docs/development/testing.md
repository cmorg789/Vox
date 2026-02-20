# Testing Guide

## Running tests

With the virtualenv active:

```bash
pytest
```

Or explicitly using the virtualenv Python:

```bash
.venv/bin/python -m pytest
```

## Test configuration

- **Framework**: pytest with pytest-asyncio.
- **Async mode**: `asyncio_mode="auto"` -- all `async def` test functions run automatically without needing the `@pytest.mark.asyncio` decorator.
- **Test directory**: `tests/`

## Test database

Tests use an **in-memory SQLite** database via aiosqlite. Each test session gets a fresh database, so tests are fully isolated and require no external services.

## Test coverage

The test suite contains 32 test files covering the following areas:

| Area            | What is tested                                          |
|-----------------|---------------------------------------------------------|
| Auth            | Registration, login, sessions, 2FA, WebAuthn.           |
| Messages        | Send, edit, delete, pin, reactions, threads.             |
| Gateway         | WebSocket connection, events, resume, heartbeat.         |
| DMs             | Direct message creation and messaging.                   |
| Voice           | Voice channel join, leave, signaling.                    |
| Federation      | Federated message exchange, peer management.             |
| Channels        | Create, update, delete, permissions.                     |
| Bots            | Bot registration, commands, interactions.                |
| E2EE            | Key upload, distribution, device management.             |
| Webhooks        | Webhook creation, execution, management.                 |
| Roles           | Role CRUD, hierarchy, permission assignment.             |
| Members         | Member list, update, kick, ban.                          |
| Permissions     | Permission calculation, overrides.                       |
| Rate limiting   | Rate limit enforcement and headers.                      |
| Sync            | Client state synchronization.                            |
| Search          | Full-text message search.                                |
| Files           | File upload and management.                              |
| Interactions    | Slash commands, buttons, modals.                         |
| Invites         | Invite creation, usage, expiry.                          |
| Moderation      | Reports, audit log, mod actions.                         |
| Notifications   | Push and in-app notification delivery.                   |
| Storage         | Storage quota and management.                            |
| Emoji           | Custom emoji upload and usage.                           |
| Embeds          | Link preview generation.                                 |
| Completeness    | API route coverage verification.                         |
| Integration     | End-to-end integration scenarios.                        |
| Dependencies    | Dependency health checks.                                |

## Writing tests

### Basic test structure

```python
import pytest

async def test_send_message(client, db_session, test_user):
    """Test that a message can be sent to a feed."""
    response = await client.post(
        "/api/feeds/1/messages",
        json={"body": "Hello, world!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["body"] == "Hello, world!"
    assert data["author_id"] == test_user.id
```

### Fixtures

The `conftest.py` file provides common fixtures:

| Fixture      | Description                                          |
|--------------|------------------------------------------------------|
| `client`     | An async HTTP test client connected to the app.      |
| `db_session` | An async SQLAlchemy session bound to the test DB.    |
| `test_user`  | A pre-created user account for authenticated tests.  |

### Tips

- All test functions should be `async def` -- pytest-asyncio handles the event loop automatically.
- Use the provided fixtures rather than creating your own database connections.
- Each test gets a clean database state; no manual teardown is needed.
- Group related tests in the same file and use descriptive function names.

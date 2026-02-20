"""SDK integration tests for bot endpoints."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


async def _make_bot(app, db_session: AsyncSession, owner_sdk, owner_reg):
    """Create a bot user account and insert the Bot DB row."""
    from vox.db.models import Bot

    bot_sdk = await make_sdk_client(app)
    bot_reg = await register(bot_sdk, "testbot", "password123")

    bot_row = Bot(
        user_id=bot_reg.user_id,
        owner_id=owner_reg.user_id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(bot_row)
    await db_session.commit()

    return bot_sdk, bot_reg


class TestBots:
    async def test_register_list_deregister_commands(self, app, db):
        from vox.db.engine import get_engine

        engine = get_engine()
        async with AsyncSession(engine) as session:
            admin = await make_sdk_client(app)
            try:
                admin_reg = await register(admin, "admin", "password123")
                bot_sdk, bot_reg = await _make_bot(app, session, admin, admin_reg)
                try:
                    # Register commands (admin calls on behalf of bot)
                    commands = [
                        {"name": "ping", "description": "Pong!"},
                        {"name": "help", "description": "Show help"},
                    ]
                    result = await admin.bots.register_commands(
                        bot_reg.user_id, commands
                    )
                    assert result.ok is True

                    # List bot commands
                    cmd_list = await admin.bots.list_bot_commands(bot_reg.user_id)
                    names = {c.name for c in cmd_list.commands}
                    assert "ping" in names
                    assert "help" in names

                    # List all commands (server-wide)
                    all_cmds = await admin.bots.list_commands()
                    assert any(c.name == "ping" for c in all_cmds.commands)

                    # Deregister one command
                    result = await admin.bots.deregister_commands(
                        bot_reg.user_id, ["ping"]
                    )
                    assert result.ok is True

                    cmd_list = await admin.bots.list_bot_commands(bot_reg.user_id)
                    names = {c.name for c in cmd_list.commands}
                    assert "ping" not in names
                    assert "help" in names
                finally:
                    await bot_sdk.close()
            finally:
                await admin.close()

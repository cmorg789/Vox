"""SDK integration tests for the gateway (live uvicorn server)."""

import asyncio

import pytest

from vox_sdk.gateway import GatewayClient
from vox_sdk.models.events import Ready

from .conftest import make_live_sdk_client, register_live

pytestmark = pytest.mark.anyio


class TestGateway:
    async def test_connect_and_ready(self, live_server):
        alice = await make_live_sdk_client(live_server)
        try:
            reg = await register_live(alice, "alice", "password123")
            gw = GatewayClient(live_server + "/gateway", alice.http.token, compress=False)
            try:
                ready = await asyncio.wait_for(gw.connect_in_background(), timeout=5)
                assert isinstance(ready, Ready)
                assert ready.session_id
                assert ready.user_id == reg.user_id
                assert isinstance(ready.server_name, str)
                assert isinstance(ready.display_name, str)
                assert ready.protocol_version >= 1
                assert isinstance(ready.capabilities, list)
            finally:
                await gw.close()
        finally:
            await alice.close()

    async def test_message_event_dispatch(self, live_server):
        alice = await make_live_sdk_client(live_server)
        bob = await make_live_sdk_client(live_server)
        try:
            await register_live(alice, "alice", "password123")
            await register_live(bob, "bob", "password123")

            feed = await alice.channels.create_feed("general")

            # Bob connects to gateway
            received = asyncio.Future()
            gw = GatewayClient(live_server + "/gateway", bob.http.token, compress=False)

            @gw.on("message_create")
            async def on_msg(event):
                if not received.done():
                    received.set_result(event)

            try:
                await asyncio.wait_for(gw.connect_in_background(), timeout=5)

                # Alice sends a message via REST
                sent = await alice.messages.send(feed.feed_id, "hello from alice")

                event = await asyncio.wait_for(received, timeout=5)
                assert event.type == "message_create"
                assert event.msg_id == sent.msg_id
                assert event.body == "hello from alice"
                assert event.feed_id == feed.feed_id
            finally:
                await gw.close()
        finally:
            await alice.close()
            await bob.close()

    async def test_event_handler_decorator(self, live_server):
        alice = await make_live_sdk_client(live_server)
        bob = await make_live_sdk_client(live_server)
        try:
            await register_live(alice, "alice", "password123")
            await register_live(bob, "bob", "password123")

            feed = await alice.channels.create_feed("general")

            specific_events = []
            wildcard_events = []
            both_done = asyncio.Event()

            gw = GatewayClient(live_server + "/gateway", bob.http.token, compress=False)

            @gw.on("message_create")
            async def on_specific(event):
                specific_events.append(event)
                if specific_events and wildcard_events:
                    both_done.set()

            @gw.on("*")
            async def on_wildcard(event):
                if event.type == "message_create":
                    wildcard_events.append(event)
                    if specific_events and wildcard_events:
                        both_done.set()

            try:
                await asyncio.wait_for(gw.connect_in_background(), timeout=5)
                await alice.messages.send(feed.feed_id, "test")
                await asyncio.wait_for(both_done.wait(), timeout=5)

                assert len(specific_events) == 1
                assert len(wildcard_events) == 1
                assert specific_events[0].msg_id == wildcard_events[0].msg_id
            finally:
                await gw.close()
        finally:
            await alice.close()
            await bob.close()

    async def test_presence_events(self, live_server):
        alice = await make_live_sdk_client(live_server)
        bob = await make_live_sdk_client(live_server)
        try:
            await register_live(alice, "alice", "password123")
            bob_reg = await register_live(bob, "bob", "password123")

            presence_events = []
            presence_received = asyncio.Event()

            gw_alice = GatewayClient(live_server + "/gateway", alice.http.token, compress=False)

            @gw_alice.on("presence_update")
            async def on_presence(event):
                if event.user_id == bob_reg.user_id:
                    presence_events.append(event)
                    presence_received.set()

            try:
                await asyncio.wait_for(gw_alice.connect_in_background(), timeout=5)

                # Bob connects — Alice should get presence_update "online"
                gw_bob = GatewayClient(live_server + "/gateway", bob.http.token, compress=False)
                try:
                    await asyncio.wait_for(gw_bob.connect_in_background(), timeout=5)
                    await asyncio.wait_for(presence_received.wait(), timeout=5)

                    assert len(presence_events) >= 1
                    assert presence_events[-1].status == "online"
                    assert presence_events[-1].user_id == bob_reg.user_id

                    # Bob disconnects — Alice should get presence_update "offline"
                    presence_received.clear()
                finally:
                    await gw_bob.close()

                await asyncio.wait_for(presence_received.wait(), timeout=5)
                assert presence_events[-1].status == "offline"
                assert presence_events[-1].user_id == bob_reg.user_id
            finally:
                await gw_alice.close()
        finally:
            await alice.close()
            await bob.close()

    async def test_multiple_event_handlers(self, live_server):
        """Register multiple handlers for the same event, both fire."""
        alice = await make_live_sdk_client(live_server)
        bob = await make_live_sdk_client(live_server)
        try:
            await register_live(alice, "alice", "password123")
            await register_live(bob, "bob", "password123")

            feed = await alice.channels.create_feed("general")

            handler_a_events = []
            handler_b_events = []
            both_done = asyncio.Event()

            gw = GatewayClient(live_server + "/gateway", bob.http.token, compress=False)

            @gw.on("message_create")
            async def handler_a(event):
                handler_a_events.append(event)
                if handler_a_events and handler_b_events:
                    both_done.set()

            @gw.on("message_create")
            async def handler_b(event):
                handler_b_events.append(event)
                if handler_a_events and handler_b_events:
                    both_done.set()

            try:
                await asyncio.wait_for(gw.connect_in_background(), timeout=5)
                await alice.messages.send(feed.feed_id, "hello")
                await asyncio.wait_for(both_done.wait(), timeout=5)

                assert len(handler_a_events) == 1
                assert len(handler_b_events) == 1
                assert handler_a_events[0].msg_id == handler_b_events[0].msg_id
            finally:
                await gw.close()
        finally:
            await alice.close()
            await bob.close()

    async def test_gateway_close(self, live_server):
        """Connect, then close, verify clean shutdown."""
        alice = await make_live_sdk_client(live_server)
        try:
            await register_live(alice, "alice", "password123")
            gw = GatewayClient(live_server + "/gateway", alice.http.token, compress=False)
            try:
                ready = await asyncio.wait_for(gw.connect_in_background(), timeout=5)
                assert isinstance(ready, Ready)
            finally:
                await gw.close()

            # After close, the WS should be None
            assert gw._ws is None
        finally:
            await alice.close()

    async def test_typing_indicator(self, live_server):
        alice = await make_live_sdk_client(live_server)
        bob = await make_live_sdk_client(live_server)
        try:
            alice_reg = await register_live(alice, "alice", "password123")
            await register_live(bob, "bob", "password123")

            feed = await alice.channels.create_feed("general")

            typing_received = asyncio.Future()
            gw_bob = GatewayClient(live_server + "/gateway", bob.http.token, compress=False)

            @gw_bob.on("typing_start")
            async def on_typing(event):
                if not typing_received.done():
                    typing_received.set_result(event)

            gw_alice = GatewayClient(live_server + "/gateway", alice.http.token, compress=False)
            try:
                await asyncio.wait_for(gw_bob.connect_in_background(), timeout=5)
                await asyncio.wait_for(gw_alice.connect_in_background(), timeout=5)

                # Alice sends typing indicator via gateway
                await gw_alice.send("typing", {"feed_id": feed.feed_id})

                event = await asyncio.wait_for(typing_received, timeout=5)
                assert event.type == "typing_start"
                assert event.feed_id == feed.feed_id
                assert event.user_id == alice_reg.user_id
            finally:
                await gw_alice.close()
                await gw_bob.close()
        finally:
            await alice.close()
            await bob.close()

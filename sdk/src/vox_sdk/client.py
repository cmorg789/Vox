"""High-level Vox client composing HTTP, Gateway, and API groups."""

from __future__ import annotations

from typing import Any

from vox_sdk.http import HTTPClient
from vox_sdk.api.auth import AuthAPI
from vox_sdk.models.auth import LoginResponse, MFARequiredResponse


class Client:
    """Top-level SDK client.

    Usage::

        async with Client("https://vox.example.com") as client:
            await client.login("user", "pass")
            msg = await client.messages.send(feed_id, "hello")
    """

    def __init__(self, base_url: str, token: str | None = None, *, timeout: float = 30.0) -> None:
        self.http = HTTPClient(base_url, token, timeout=timeout)
        self.auth = AuthAPI(self.http)

        # Lazily populated API groups (Phase 2+)
        self._messages: Any = None
        self._channels: Any = None
        self._members: Any = None
        self._roles: Any = None
        self._server: Any = None
        self._users: Any = None
        self._invites: Any = None
        self._voice: Any = None
        self._dms: Any = None
        self._webhooks: Any = None
        self._bots: Any = None
        self._e2ee: Any = None
        self._moderation: Any = None
        self._files: Any = None
        self._federation: Any = None
        self._search: Any = None
        self._emoji: Any = None
        self._sync: Any = None
        self._embeds: Any = None

        self._gateway: Any = None

    # --- Convenience login ---

    async def login(self, username: str, password: str) -> LoginResponse | MFARequiredResponse:
        """Login and store the token for subsequent requests."""
        result = await self.auth.login(username, password)
        if isinstance(result, LoginResponse):
            self.http.token = result.token
        return result

    # --- API group properties ---

    @property
    def messages(self) -> Any:
        if self._messages is None:
            from vox_sdk.api.messages import MessagesAPI
            self._messages = MessagesAPI(self.http)
        return self._messages

    @property
    def channels(self) -> Any:
        if self._channels is None:
            from vox_sdk.api.channels import ChannelsAPI
            self._channels = ChannelsAPI(self.http)
        return self._channels

    @property
    def members(self) -> Any:
        if self._members is None:
            from vox_sdk.api.members import MembersAPI
            self._members = MembersAPI(self.http)
        return self._members

    @property
    def roles(self) -> Any:
        if self._roles is None:
            from vox_sdk.api.roles import RolesAPI
            self._roles = RolesAPI(self.http)
        return self._roles

    @property
    def server(self) -> Any:
        if self._server is None:
            from vox_sdk.api.server import ServerAPI
            self._server = ServerAPI(self.http)
        return self._server

    @property
    def users(self) -> Any:
        if self._users is None:
            from vox_sdk.api.users import UsersAPI
            self._users = UsersAPI(self.http)
        return self._users

    @property
    def invites(self) -> Any:
        if self._invites is None:
            from vox_sdk.api.invites import InvitesAPI
            self._invites = InvitesAPI(self.http)
        return self._invites

    @property
    def voice(self) -> Any:
        if self._voice is None:
            from vox_sdk.api.voice import VoiceAPI
            self._voice = VoiceAPI(self.http)
        return self._voice

    @property
    def dms(self) -> Any:
        if self._dms is None:
            from vox_sdk.api.dms import DMsAPI
            self._dms = DMsAPI(self.http)
        return self._dms

    @property
    def webhooks(self) -> Any:
        if self._webhooks is None:
            from vox_sdk.api.webhooks import WebhooksAPI
            self._webhooks = WebhooksAPI(self.http)
        return self._webhooks

    @property
    def bots(self) -> Any:
        if self._bots is None:
            from vox_sdk.api.bots import BotsAPI
            self._bots = BotsAPI(self.http)
        return self._bots

    @property
    def e2ee(self) -> Any:
        if self._e2ee is None:
            from vox_sdk.api.e2ee import E2EEAPI
            self._e2ee = E2EEAPI(self.http)
        return self._e2ee

    @property
    def moderation(self) -> Any:
        if self._moderation is None:
            from vox_sdk.api.moderation import ModerationAPI
            self._moderation = ModerationAPI(self.http)
        return self._moderation

    @property
    def files(self) -> Any:
        if self._files is None:
            from vox_sdk.api.files import FilesAPI
            self._files = FilesAPI(self.http)
        return self._files

    @property
    def federation(self) -> Any:
        if self._federation is None:
            from vox_sdk.api.federation import FederationAPI
            self._federation = FederationAPI(self.http)
        return self._federation

    @property
    def search(self) -> Any:
        if self._search is None:
            from vox_sdk.api.search import SearchAPI
            self._search = SearchAPI(self.http)
        return self._search

    @property
    def emoji(self) -> Any:
        if self._emoji is None:
            from vox_sdk.api.emoji import EmojiAPI
            self._emoji = EmojiAPI(self.http)
        return self._emoji

    @property
    def sync(self) -> Any:
        if self._sync is None:
            from vox_sdk.api.sync import SyncAPI
            self._sync = SyncAPI(self.http)
        return self._sync

    @property
    def embeds(self) -> Any:
        if self._embeds is None:
            from vox_sdk.api.embeds import EmbedsAPI
            self._embeds = EmbedsAPI(self.http)
        return self._embeds

    # --- Gateway ---

    async def connect_gateway(self, **kwargs: Any) -> Any:
        """Connect to the WebSocket gateway.

        Fetches the gateway URL from the server's discovery endpoint
        before establishing the WebSocket connection.
        """
        from vox_sdk.gateway import GatewayClient
        if self.http.token is None:
            raise RuntimeError("Must be logged in before connecting to gateway")
        info = await self.server.gateway_info()
        self._gateway = GatewayClient(info.url, self.http.token, **kwargs)
        await self._gateway.run()
        return self._gateway

    # --- Context manager ---

    async def close(self) -> None:
        if self._gateway is not None:
            await self._gateway.close()
        await self.http.close()

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

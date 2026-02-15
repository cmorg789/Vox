"""Ephemeral in-memory interaction store with TTL."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

INTERACTION_TTL = 15  # seconds


@dataclass
class Interaction:
    id: str
    type: str  # "slash_command" | "button"
    command: str | None
    params: dict
    user_id: int
    feed_id: int | None
    dm_id: int | None
    bot_id: int
    created_at: float = field(default_factory=time.time)


_store: dict[str, Interaction] = {}


def create(
    type: str,
    command: str | None,
    params: dict,
    user_id: int,
    feed_id: int | None,
    dm_id: int | None,
    bot_id: int,
) -> Interaction:
    interaction = Interaction(
        id=secrets.token_urlsafe(16),
        type=type,
        command=command,
        params=params,
        user_id=user_id,
        feed_id=feed_id,
        dm_id=dm_id,
        bot_id=bot_id,
    )
    _store[interaction.id] = interaction
    return interaction


def get(interaction_id: str) -> Interaction | None:
    interaction = _store.get(interaction_id)
    if interaction is None:
        return None
    if time.time() - interaction.created_at > INTERACTION_TTL:
        del _store[interaction_id]
        return None
    return interaction


def consume(interaction_id: str) -> Interaction | None:
    interaction = get(interaction_id)
    if interaction is not None:
        del _store[interaction_id]
    return interaction


def reset() -> None:
    _store.clear()

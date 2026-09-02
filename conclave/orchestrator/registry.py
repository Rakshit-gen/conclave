"""Tracks which A2A agents are known and what they can do, so a workflow can
delegate by capability instead of hardcoding a URL for every step.
"""

from __future__ import annotations

from conclave.a2a.client import AgentClient
from conclave.a2a.models import AgentCard


class AgentRegistry:
    def __init__(self) -> None:
        self._cards: dict[str, AgentCard] = {}

    async def register(self, base_url: str) -> AgentCard:
        client = AgentClient(base_url)
        try:
            card = await client.discover()
        finally:
            await client.aclose()
        self._cards[base_url] = card
        return card

    def get(self, base_url: str) -> AgentCard | None:
        return self._cards.get(base_url)

    def find_by_skill(self, tag: str) -> list[str]:
        return [
            url
            for url, card in self._cards.items()
            if any(tag in skill.tags for skill in card.skills)
        ]

    def urls(self) -> list[str]:
        return list(self._cards.keys())

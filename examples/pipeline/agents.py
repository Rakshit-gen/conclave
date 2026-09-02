"""Three small, deliberately dependency-free agents for the pipeline demo.

Each one's "intelligence" is a plain deterministic string transform, not a
model call — on purpose. This demo exists to prove the orchestration layer
(real A2A over real HTTP, real durability, real crash recovery), and a
canned LLM call would add cost, flakiness, and an API key requirement
without making any of that more convincing. Swap `handler` for a real model
call and nothing else in this package needs to change.
"""

from __future__ import annotations

from conclave.a2a import AgentServer
from conclave.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Message,
    Part,
)

from .config import PORTS


def _text_of(message: Message) -> str:
    return "".join(p.text or "" for p in message.parts)


async def _research_handler(message: Message) -> list[Part]:
    topic = _text_of(message).strip()
    bullets = [
        f"{topic} has a well-documented history worth summarizing.",
        f"There are at least two competing schools of thought on {topic}.",
        f"Recent developments in {topic} are relevant to a general audience.",
    ]
    return [Part.of_text("\n".join(f"- {b}" for b in bullets))]


async def _writer_handler(message: Message) -> list[Part]:
    bullets = _text_of(message).strip()
    lines = [line.removeprefix("- ") for line in bullets.splitlines() if line.strip()]
    draft = " ".join(lines)
    return [Part.of_text(draft)]


async def _reviewer_handler(message: Message) -> list[Part]:
    draft = _text_of(message).strip()
    polished = draft[0].upper() + draft[1:] if draft else draft
    if not polished.endswith((".", "!", "?")):
        polished += "."
    return [Part.of_text(polished)]


def researcher_server() -> AgentServer:
    card = AgentCard(
        name="Researcher",
        description="Gathers a few bullet points of background on a topic.",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{PORTS['researcher']}")],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="research",
                name="Research a topic",
                description="Returns a short bulleted list of background facts.",
                tags=["research"],
            )
        ],
    )
    return AgentServer(card, _research_handler)


def writer_server() -> AgentServer:
    card = AgentCard(
        name="Writer",
        description="Turns bullet points into a short prose draft.",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{PORTS['writer']}")],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="write",
                name="Draft prose",
                description="Turns bullet points into a single draft paragraph.",
                tags=["writing"],
            )
        ],
    )
    return AgentServer(card, _writer_handler)


def reviewer_server() -> AgentServer:
    card = AgentCard(
        name="Reviewer",
        description="Polishes a draft's capitalization and terminal punctuation.",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{PORTS['reviewer']}")],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="review",
                name="Polish a draft",
                description="Fixes capitalization and ensures terminal punctuation.",
                tags=["review"],
            )
        ],
    )
    return AgentServer(card, _reviewer_handler)

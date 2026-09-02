from __future__ import annotations

from conclave.a2a.models import Message, Part, Role
from conclave.orchestrator import delegate


async def delegate_text(agent_url: str, text: str, *, name: str) -> str:
    """`delegate()` plus the single-text-part unwrap every agent in this
    demo happens to use — keeps workflow.py reading as plain business logic.
    """
    task = await delegate(agent_url, Message(role=Role.USER, parts=[Part.of_text(text)]), name=name)
    return "".join(p.text or "" for p in task.artifacts[0].parts)

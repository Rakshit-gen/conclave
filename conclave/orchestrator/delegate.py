"""The one primitive that makes cross-agent delegation durable: a whole
send-message-and-wait-for-the-task-to-finish round trip is recorded as a
single step, so replaying a crashed workflow never re-sends a message an
agent already received and (maybe irreversibly) acted on.
"""

from __future__ import annotations

from conclave.a2a.client import AgentClient
from conclave.a2a.models import Message, Task
from conclave.core import step


async def delegate(agent_url: str, message: Message, *, name: str | None = None) -> Task:
    step_name = name or f"delegate:{agent_url}:{message.message_id}"

    async def _send_and_wait() -> dict:
        client = AgentClient(agent_url)
        try:
            task = await client.send_message(message)
        finally:
            await client.aclose()
        return task.model_dump(mode="json", by_alias=True, exclude_none=True)

    raw_task = await step(_send_and_wait, name=step_name)
    return Task.model_validate(raw_task)

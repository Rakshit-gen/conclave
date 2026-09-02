"""A client for the A2A HTTP+JSON REST binding: discover an agent, send it a
message, poll or stream the resulting task.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .models import (
    AgentCard,
    Message,
    SendMessageConfiguration,
    SendMessageRequest,
    StreamResponse,
    Task,
)


class AgentClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def discover(self) -> AgentCard:
        response = await self._client.get(f"{self.base_url}/.well-known/agent-card.json")
        response.raise_for_status()
        return AgentCard.model_validate(response.json())

    async def send_message(
        self, message: Message, configuration: SendMessageConfiguration | None = None
    ) -> Task:
        request = SendMessageRequest(message=message, configuration=configuration)
        response = await self._client.post(
            f"{self.base_url}/message:send",
            json=request.model_dump(by_alias=True, exclude_none=True),
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def stream_message(
        self, message: Message, configuration: SendMessageConfiguration | None = None
    ) -> AsyncIterator[StreamResponse]:
        request = SendMessageRequest(message=message, configuration=configuration)
        async with self._client.stream(
            "POST",
            f"{self.base_url}/message:stream",
            json=request.model_dump(by_alias=True, exclude_none=True),
        ) as response:
            response.raise_for_status()
            async for payload in _iter_sse_data(response):
                yield StreamResponse.model_validate(json.loads(payload))

    async def get_task(self, task_id: str) -> Task:
        response = await self._client.get(f"{self.base_url}/tasks/{task_id}")
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def cancel_task(self, task_id: str) -> Task:
        response = await self._client.post(f"{self.base_url}/tasks/{task_id}:cancel")
        response.raise_for_status()
        return Task.model_validate(response.json())


async def _iter_sse_data(response: httpx.Response) -> AsyncIterator[str]:
    """Minimal `text/event-stream` framing: `data: ...` lines, blank-line
    terminated. Multi-line `data:` fields are joined with `\\n`, per the
    SSE spec — small enough not to need a dependency for it.
    """
    buffer: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if buffer:
                yield "\n".join(buffer)
                buffer = []
            continue
        if line.startswith("data:"):
            buffer.append(line[len("data:") :].lstrip())
    if buffer:
        yield "\n".join(buffer)

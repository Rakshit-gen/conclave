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
    TaskPushNotificationConfig,
)


class AgentClient:
    def __init__(
        self,
        base_url: str,
        http_client: httpx.AsyncClient | None = None,
        auth_headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._auth_headers = auth_headers or {}
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
            headers=self._auth_headers,
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
            headers=self._auth_headers,
        ) as response:
            response.raise_for_status()
            async for payload in _iter_sse_data(response):
                yield StreamResponse.model_validate(json.loads(payload))

    async def subscribe_task(self, task_id: str) -> AsyncIterator[StreamResponse]:
        async with self._client.stream(
            "GET", f"{self.base_url}/tasks/{task_id}:subscribe", headers=self._auth_headers
        ) as response:
            response.raise_for_status()
            async for payload in _iter_sse_data(response):
                yield StreamResponse.model_validate(json.loads(payload))

    async def get_task(self, task_id: str) -> Task:
        response = await self._client.get(
            f"{self.base_url}/tasks/{task_id}", headers=self._auth_headers
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def cancel_task(self, task_id: str) -> Task:
        response = await self._client.post(
            f"{self.base_url}/tasks/{task_id}:cancel", headers=self._auth_headers
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def create_push_notification_config(
        self, task_id: str, config: TaskPushNotificationConfig
    ) -> TaskPushNotificationConfig:
        response = await self._client.post(
            f"{self.base_url}/tasks/{task_id}/pushNotificationConfigs",
            json=config.model_dump(by_alias=True, exclude_none=True),
            headers=self._auth_headers,
        )
        response.raise_for_status()
        return TaskPushNotificationConfig.model_validate(response.json())

    async def list_push_notification_configs(
        self, task_id: str
    ) -> list[TaskPushNotificationConfig]:
        response = await self._client.get(
            f"{self.base_url}/tasks/{task_id}/pushNotificationConfigs", headers=self._auth_headers
        )
        response.raise_for_status()
        return [TaskPushNotificationConfig.model_validate(c) for c in response.json()["configs"]]

    async def delete_push_notification_config(self, task_id: str, config_id: str) -> None:
        response = await self._client.delete(
            f"{self.base_url}/tasks/{task_id}/pushNotificationConfigs/{config_id}",
            headers=self._auth_headers,
        )
        response.raise_for_status()


def api_key_headers(header_name: str, key: str) -> dict[str, str]:
    return {header_name: key}


def bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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

"""A client for the A2A JSON-RPC 2.0 binding — same operations as
`AgentClient`, dispatched through one `/jsonrpc` endpoint instead of a
route per operation. Agent Card discovery still uses the REST `.well-known`
path regardless of transport; that's how a client learns which bindings an
agent even offers.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import AsyncIterator

import httpx

from .models import (
    AgentCard,
    Message,
    SendMessageConfiguration,
    Task,
    TaskPushNotificationConfig,
)

_ids = itertools.count(1)


class JsonRpcError(RuntimeError):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(f"JSON-RPC error {code}: {message}")


class JsonRpcAgentClient:
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

    async def _call(self, method: str, params: dict) -> dict:
        request_id = next(_ids)
        response = await self._client.post(
            f"{self.base_url}/jsonrpc",
            json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            headers=self._auth_headers,
        )
        response.raise_for_status()
        envelope = response.json()
        if "error" in envelope:
            raise JsonRpcError(envelope["error"]["code"], envelope["error"]["message"])
        return envelope["result"]

    async def _call_stream(self, method: str, params: dict) -> AsyncIterator[dict]:
        request_id = next(_ids)
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        async with self._client.stream(
            "POST", f"{self.base_url}/jsonrpc", json=body, headers=self._auth_headers
        ) as response:
            response.raise_for_status()
            buffer: list[str] = []
            async for line in response.aiter_lines():
                if line == "":
                    if buffer:
                        envelope = json.loads("\n".join(buffer))
                        buffer = []
                        error = envelope.get("error")
                        if error is not None:
                            raise JsonRpcError(error["code"], error["message"])
                        yield envelope["result"]
                    continue
                if line.startswith("data:"):
                    buffer.append(line[len("data:") :].lstrip())

    async def send_message(
        self, message: Message, configuration: SendMessageConfiguration | None = None
    ) -> Task:
        params = {"message": message.model_dump(mode="json", by_alias=True, exclude_none=True)}
        if configuration is not None:
            params["configuration"] = configuration.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        result = await self._call("SendMessage", params)
        return Task.model_validate(result)

    async def stream_message(
        self, message: Message, configuration: SendMessageConfiguration | None = None
    ) -> AsyncIterator[dict]:
        params = {"message": message.model_dump(mode="json", by_alias=True, exclude_none=True)}
        if configuration is not None:
            params["configuration"] = configuration.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        async for event in self._call_stream("SendStreamingMessage", params):
            yield event

    async def subscribe_task(self, task_id: str) -> AsyncIterator[dict]:
        async for event in self._call_stream("SubscribeToTask", {"id": task_id}):
            yield event

    async def get_task(self, task_id: str) -> Task:
        return Task.model_validate(await self._call("GetTask", {"id": task_id}))

    async def list_tasks(self) -> list[Task]:
        result = await self._call("ListTasks", {})
        return [Task.model_validate(t) for t in result["tasks"]]

    async def cancel_task(self, task_id: str) -> Task:
        return Task.model_validate(await self._call("CancelTask", {"id": task_id}))

    async def create_push_notification_config(
        self, task_id: str, config: TaskPushNotificationConfig
    ) -> TaskPushNotificationConfig:
        params = config.model_copy(update={"task_id": task_id}).model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        return TaskPushNotificationConfig.model_validate(
            await self._call("CreateTaskPushNotificationConfig", params)
        )

    async def list_push_notification_configs(
        self, task_id: str
    ) -> list[TaskPushNotificationConfig]:
        result = await self._call("ListTaskPushNotificationConfigs", {"task_id": task_id})
        return [TaskPushNotificationConfig.model_validate(c) for c in result["configs"]]

    async def delete_push_notification_config(self, task_id: str, config_id: str) -> None:
        await self._call("DeleteTaskPushNotificationConfig", {"task_id": task_id, "id": config_id})

    async def get_extended_agent_card(self) -> AgentCard:
        return AgentCard.model_validate(await self._call("GetExtendedAgentCard", {}))

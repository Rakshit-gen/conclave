"""Push notification config storage and webhook delivery.

`TaskPushNotificationConfig` (spec §4.3.1) lets a client ask to be told
about a task's status changes via a webhook instead of polling or holding
an SSE connection open. Delivery failures are swallowed on purpose — a
client's dead webhook shouldn't be able to break task execution for
anyone else, or for the task itself.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

import httpx

from .models import Task, TaskPushNotificationConfig, TaskStatusUpdateEvent


class PushNotificationStore(ABC):
    @abstractmethod
    def put(self, task_id: str, config: TaskPushNotificationConfig) -> None: ...

    @abstractmethod
    def get(self, task_id: str, config_id: str) -> TaskPushNotificationConfig | None: ...

    @abstractmethod
    def for_task(self, task_id: str) -> list[TaskPushNotificationConfig]: ...

    @abstractmethod
    def delete(self, task_id: str, config_id: str) -> bool: ...


class InMemoryPushNotificationStore(PushNotificationStore):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[str, dict[str, TaskPushNotificationConfig]] = {}

    def put(self, task_id: str, config: TaskPushNotificationConfig) -> None:
        with self._lock:
            self._configs.setdefault(task_id, {})[config.id] = config

    def get(self, task_id: str, config_id: str) -> TaskPushNotificationConfig | None:
        with self._lock:
            return self._configs.get(task_id, {}).get(config_id)

    def for_task(self, task_id: str) -> list[TaskPushNotificationConfig]:
        with self._lock:
            return list(self._configs.get(task_id, {}).values())

    def delete(self, task_id: str, config_id: str) -> bool:
        with self._lock:
            return self._configs.get(task_id, {}).pop(config_id, None) is not None


class PushNotifier(ABC):
    @abstractmethod
    async def notify(self, config: TaskPushNotificationConfig, task: Task) -> None: ...


class HttpPushNotifier(PushNotifier):
    """POSTs a `TaskStatusUpdateEvent` to the configured webhook URL,
    carrying `authentication` (spec §4.3.2) as an `Authorization` header
    when the scheme is one that maps onto one (Bearer, Basic, or any other
    IANA HTTP auth scheme name) — which is all the spec actually defines
    for push-notification auth.
    """

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 5.0):
        self._client = client
        self._timeout = timeout
        self._owns_client = client is None

    async def notify(self, config: TaskPushNotificationConfig, task: Task) -> None:
        event = TaskStatusUpdateEvent(
            task_id=task.id, context_id=task.context_id or "", status=task.status
        )
        headers = {}
        if config.authentication is not None:
            auth = config.authentication
            headers["Authorization"] = f"{auth.scheme} {auth.credentials}"
        if config.token:
            headers["X-Conclave-Push-Token"] = config.token

        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            await client.post(
                config.url,
                json=event.model_dump(mode="json", by_alias=True, exclude_none=True),
                headers=headers,
            )
        except httpx.HTTPError:
            pass  # a client's unreachable webhook must not break task execution
        finally:
            if self._owns_client:
                await client.aclose()

"""Exposes a single local agent over the A2A HTTP+JSON REST binding.

Route table mirrors docs/a2a-spec-notes.md exactly. An `AgentHandler` is
the only thing a caller has to supply: given the incoming `Message`, return
the `Part`s of its answer (or raise, for a failed task). Task lifecycle,
push notification delivery, and SSE framing all live in `TaskRunner` —
this module is just the HTTP adapter over it.
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from .auth import AuthenticationError, Authenticator, NoAuth
from .jsonrpc import JsonRpcDispatcher, is_streaming_method
from .models import AgentCard, SendMessageRequest, StreamResponse, TaskPushNotificationConfig
from .push import (
    HttpPushNotifier,
    InMemoryPushNotificationStore,
    PushNotificationStore,
    PushNotifier,
)
from .runner import AgentHandler, TaskAlreadyTerminalError, TaskNotFoundError, TaskRunner
from .tasks import InMemoryTaskStore, TaskStore


class AgentServer:
    """One agent, one FastAPI app."""

    def __init__(
        self,
        card: AgentCard,
        handler: AgentHandler,
        task_store: TaskStore | None = None,
        push_configs: PushNotificationStore | None = None,
        notifier: PushNotifier | None = None,
        authenticator: Authenticator | None = None,
    ):
        self.card = card
        self.push_configs = push_configs or InMemoryPushNotificationStore()
        self.runner = TaskRunner(
            handler,
            task_store or InMemoryTaskStore(),
            self.push_configs,
            notifier or HttpPushNotifier(),
        )
        self.authenticator = authenticator or NoAuth()
        self.jsonrpc = JsonRpcDispatcher(
            self.card, self.runner, self.push_configs, self.authenticator
        )
        self.app = FastAPI(title=card.name)
        self._mount_routes()

    @property
    def tasks(self) -> TaskStore:
        return self.runner.tasks

    def _require_auth(self, request: Request) -> None:
        try:
            self.authenticator.authenticate({k.lower(): v for k, v in request.headers.items()})
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def _mount_routes(self) -> None:
        app = self.app

        @app.get("/.well-known/agent-card.json")
        async def get_agent_card() -> dict:
            return self.card.model_dump(by_alias=True, exclude_none=True)

        @app.post("/jsonrpc")
        async def jsonrpc_endpoint(http_request: Request):
            envelope = await http_request.json()
            headers = {k.lower(): v for k, v in http_request.headers.items()}
            method = envelope.get("method")
            if is_streaming_method(method):
                frames = self.jsonrpc.dispatch_stream(envelope, headers)
                return EventSourceResponse(_as_jsonrpc_sse(frames))
            return await self.jsonrpc.dispatch(envelope, headers)

        @app.post("/message:send")
        async def send_message(request: SendMessageRequest, http_request: Request) -> dict:
            self._require_auth(http_request)
            push_config = None
            return_immediately = False
            if request.configuration is not None:
                push_config = request.configuration.task_push_notification_config
                return_immediately = request.configuration.return_immediately
            task = await self.runner.run(
                request.message, push_config=push_config, return_immediately=return_immediately
            )
            return task.model_dump(by_alias=True, exclude_none=True)

        @app.post("/message:stream")
        async def send_message_stream(request: SendMessageRequest, http_request: Request):
            self._require_auth(http_request)
            return EventSourceResponse(_as_sse(self.runner.stream(request.message)))

        @app.get("/tasks/{task_id}:subscribe")
        async def subscribe_task(task_id: str, http_request: Request):
            self._require_auth(http_request)
            try:
                events = self.runner.subscribe(task_id)
                first = await events.__anext__()
            except TaskNotFoundError as exc:
                raise HTTPException(status_code=404, detail=f"no such task {task_id!r}") from exc
            except TaskAlreadyTerminalError as exc:
                raise HTTPException(
                    status_code=409, detail=f"task {task_id!r} is already in a terminal state"
                ) from exc
            return EventSourceResponse(_as_sse(_prepend(first, events)))

        @app.get("/tasks/{task_id}")
        async def get_task(task_id: str, http_request: Request) -> dict:
            self._require_auth(http_request)
            task = self.runner.get(task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"no such task {task_id!r}")
            return task.model_dump(by_alias=True, exclude_none=True)

        @app.get("/tasks")
        async def list_tasks(http_request: Request) -> dict:
            self._require_auth(http_request)
            dumped = [t.model_dump(by_alias=True, exclude_none=True) for t in self.runner.list()]
            return {"tasks": dumped}

        @app.post("/tasks/{task_id}:cancel")
        async def cancel_task(task_id: str, http_request: Request) -> dict:
            self._require_auth(http_request)
            task = self.runner.cancel(task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"no such task {task_id!r}")
            return task.model_dump(by_alias=True, exclude_none=True)

        @app.post("/tasks/{task_id}/pushNotificationConfigs")
        async def create_push_config(
            task_id: str, config: TaskPushNotificationConfig, http_request: Request
        ) -> dict:
            self._require_auth(http_request)
            config = config.model_copy(update={"task_id": task_id})
            self.push_configs.put(task_id, config)
            return config.model_dump(by_alias=True, exclude_none=True)

        @app.get("/tasks/{task_id}/pushNotificationConfigs/{config_id}")
        async def get_push_config(task_id: str, config_id: str, http_request: Request) -> dict:
            self._require_auth(http_request)
            config = self.push_configs.get(task_id, config_id)
            if config is None:
                raise HTTPException(status_code=404, detail="no such push notification config")
            return config.model_dump(by_alias=True, exclude_none=True)

        @app.get("/tasks/{task_id}/pushNotificationConfigs")
        async def list_push_configs(task_id: str, http_request: Request) -> dict:
            self._require_auth(http_request)
            configs = self.push_configs.for_task(task_id)
            return {"configs": [c.model_dump(by_alias=True, exclude_none=True) for c in configs]}

        @app.delete("/tasks/{task_id}/pushNotificationConfigs/{config_id}")
        async def delete_push_config(task_id: str, config_id: str, http_request: Request) -> dict:
            self._require_auth(http_request)
            if not self.push_configs.delete(task_id, config_id):
                raise HTTPException(status_code=404, detail="no such push notification config")
            return {}


async def _as_sse(responses):
    async for response in responses:
        yield _frame(response)


async def _as_jsonrpc_sse(envelopes):
    async for envelope in envelopes:
        yield {"data": json.dumps(envelope)}


async def _prepend(first, rest):
    """Re-attaches an item already pulled off `rest` (to surface a 404/409
    *before* the SSE response starts, instead of mid-stream) back onto it.
    """
    yield first
    async for item in rest:
        yield item


def _frame(response: StreamResponse) -> dict:
    return {"data": json.dumps(response.model_dump(mode="json", by_alias=True, exclude_none=True))}

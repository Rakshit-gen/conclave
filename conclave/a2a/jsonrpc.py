"""JSON-RPC 2.0 binding (spec §9): the same eleven methods as the REST
binding's routes, dispatched through one POST endpoint instead of a route
per operation. Same `TaskRunner`, same auth, same push-notification store
as the REST binding on the same `AgentServer` — this is a second front
door onto identical behavior, not a second implementation of it.

Error codes use JSON-RPC 2.0's reserved "server error" range (-32000 to
-32099, spec-reserved for implementation-defined errors) for app-level
failures, and the standard codes for framing failures.
"""

from __future__ import annotations

from typing import Any

from .auth import AuthenticationError, Authenticator
from .models import (
    AgentCard,
    Message,
    SendMessageConfiguration,
    SendMessageRequest,
    Task,
    TaskPushNotificationConfig,
)
from .push import PushNotificationStore
from .runner import TaskAlreadyTerminalError, TaskNotFoundError, TaskRunner

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
UNAUTHENTICATED = -32001
TASK_NOT_FOUND = -32002
TASK_ALREADY_TERMINAL = -32003

_STREAMING_METHODS = {"SendStreamingMessage", "SubscribeToTask"}


def is_streaming_method(method: str) -> bool:
    return method in _STREAMING_METHODS


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _result(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


class JsonRpcDispatcher:
    def __init__(
        self,
        card: AgentCard,
        runner: TaskRunner,
        push_configs: PushNotificationStore,
        authenticator: Authenticator,
    ):
        self.card = card
        self.runner = runner
        self.push_configs = push_configs
        self.authenticator = authenticator

    def _check_auth(self, headers: dict[str, str]) -> None:
        self.authenticator.authenticate(headers)

    async def dispatch(self, envelope: dict, headers: dict[str, str]) -> dict:
        request_id = envelope.get("id")
        method = envelope.get("method")
        params = envelope.get("params") or {}

        if envelope.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return _error(request_id, INVALID_REQUEST, "not a valid JSON-RPC 2.0 request")

        try:
            self._check_auth(headers)
        except AuthenticationError as exc:
            return _error(request_id, UNAUTHENTICATED, str(exc))

        handler = _METHODS.get(method)
        if handler is None:
            return _error(request_id, METHOD_NOT_FOUND, f"unknown method {method!r}")

        try:
            result = await handler(self, params)
        except TaskNotFoundError as exc:
            return _error(request_id, TASK_NOT_FOUND, f"no such task {exc}")
        except TaskAlreadyTerminalError as exc:
            return _error(request_id, TASK_ALREADY_TERMINAL, f"task {exc} is already terminal")
        except (KeyError, TypeError, ValueError) as exc:
            return _error(request_id, INVALID_PARAMS, str(exc))
        return _result(request_id, result)

    async def dispatch_stream(self, envelope: dict, headers: dict[str, str]):
        """For SendStreamingMessage / SubscribeToTask: each yielded item is
        itself a full JSON-RPC response object, one per `StreamResponse`.
        """
        request_id = envelope.get("id")
        method = envelope.get("method")
        params = envelope.get("params") or {}

        try:
            self._check_auth(headers)
        except AuthenticationError as exc:
            yield _error(request_id, UNAUTHENTICATED, str(exc))
            return

        def dump(event):
            return event.model_dump(mode="json", by_alias=True, exclude_none=True)

        try:
            if method == "SendStreamingMessage":
                message = Message.model_validate(params["message"])
                async for event in self.runner.stream(message):
                    yield _result(request_id, dump(event))
            elif method == "SubscribeToTask":
                async for event in self.runner.subscribe(params["id"]):
                    yield _result(request_id, dump(event))
            else:
                yield _error(request_id, METHOD_NOT_FOUND, f"unknown streaming method {method!r}")
        except TaskNotFoundError as exc:
            yield _error(request_id, TASK_NOT_FOUND, f"no such task {exc}")
        except TaskAlreadyTerminalError as exc:
            yield _error(request_id, TASK_ALREADY_TERMINAL, f"task {exc} is already terminal")


async def _send_message(self: JsonRpcDispatcher, params: dict) -> dict:
    request = SendMessageRequest(
        message=Message.model_validate(params["message"]),
        configuration=SendMessageConfiguration.model_validate(params["configuration"])
        if params.get("configuration")
        else None,
    )
    push_config = None
    return_immediately = False
    if request.configuration is not None:
        push_config = request.configuration.task_push_notification_config
        return_immediately = request.configuration.return_immediately
    task = await self.runner.run(
        request.message, push_config=push_config, return_immediately=return_immediately
    )
    return task.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _get_task(self: JsonRpcDispatcher, params: dict) -> dict:
    task = self.runner.get(params["id"])
    if task is None:
        raise TaskNotFoundError(params["id"])
    return task.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _list_tasks(self: JsonRpcDispatcher, params: dict) -> dict:
    tasks: list[Task] = self.runner.list()
    return {
        "tasks": [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in tasks],
        "nextPageToken": "",
        "pageSize": len(tasks),
        "totalSize": len(tasks),
    }


async def _cancel_task(self: JsonRpcDispatcher, params: dict) -> dict:
    task = self.runner.cancel(params["id"])
    if task is None:
        raise TaskNotFoundError(params["id"])
    return task.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _create_push_config(self: JsonRpcDispatcher, params: dict) -> dict:
    config = TaskPushNotificationConfig.model_validate(params)
    self.push_configs.put(config.task_id or "", config)
    return config.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _get_push_config(self: JsonRpcDispatcher, params: dict) -> dict:
    config = self.push_configs.get(params["task_id"], params["id"])
    if config is None:
        raise TaskNotFoundError(f"push config {params['id']!r} on task {params['task_id']!r}")
    return config.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _list_push_configs(self: JsonRpcDispatcher, params: dict) -> dict:
    configs = self.push_configs.for_task(params["task_id"])
    dumped = [c.model_dump(mode="json", by_alias=True, exclude_none=True) for c in configs]
    return {"configs": dumped}


async def _delete_push_config(self: JsonRpcDispatcher, params: dict) -> dict:
    self.push_configs.delete(params["task_id"], params["id"])
    return {}


async def _get_extended_agent_card(self: JsonRpcDispatcher, params: dict) -> dict:
    return self.card.model_dump(mode="json", by_alias=True, exclude_none=True)


_METHODS = {
    "SendMessage": _send_message,
    "GetTask": _get_task,
    "ListTasks": _list_tasks,
    "CancelTask": _cancel_task,
    "CreateTaskPushNotificationConfig": _create_push_config,
    "GetTaskPushNotificationConfig": _get_push_config,
    "ListTaskPushNotificationConfigs": _list_push_configs,
    "DeleteTaskPushNotificationConfig": _delete_push_config,
    "GetExtendedAgentCard": _get_extended_agent_card,
}

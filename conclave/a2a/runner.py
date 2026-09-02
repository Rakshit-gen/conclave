"""Transport-agnostic task lifecycle: everything a binding (REST, JSON-RPC,
gRPC) needs, so none of them re-implement task-state bookkeeping, push
notification delivery, or SSE/subscription fan-out themselves — they just
adapt their wire format to these calls.

Task execution always runs as a background `asyncio.Task`, not inline in
the call that created it. That's what makes `return_immediately=True` and
`/tasks/{id}:subscribe` (attaching to a task a *different* request started)
genuine rather than modeled-but-unreachable: with synchronous-only
execution there's never a moment where a task is running but nobody's
awaiting it yet.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from .models import (
    Artifact,
    Message,
    Part,
    Role,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from .push import PushNotificationStore, PushNotifier
from .tasks import TaskStore

AgentHandler = Callable[[Message], Awaitable[list[Part]]]


class TaskNotFoundError(LookupError):
    pass


class TaskAlreadyTerminalError(RuntimeError):
    """Raised by `subscribe()` — the spec reserves subscription for tasks
    not yet in a terminal state; a finished task's result is a GET away.
    """


class TaskRunner:
    def __init__(
        self,
        handler: AgentHandler,
        task_store: TaskStore,
        push_configs: PushNotificationStore,
        notifier: PushNotifier,
    ):
        self.handler = handler
        self.tasks = task_store
        self.push_configs = push_configs
        self.notifier = notifier
        self._subscribers: dict[str, list[asyncio.Queue[StreamResponse]]] = {}
        self._background: set[asyncio.Task] = set()

    def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def list(self) -> list[Task]:
        return self.tasks.list()

    def cancel(self, task_id: str) -> Task | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        if not task.status.state.is_terminal:
            task = task.model_copy(update={"status": TaskStatus(state=TaskState.CANCELED)})
            self.tasks.put(task)
        return task

    async def _put_and_notify(self, task: Task, event: StreamResponse) -> None:
        self.tasks.put(task)
        for config in self.push_configs.for_task(task.id):
            await self.notifier.notify(config, task)
        for queue in self._subscribers.get(task.id, []):
            await queue.put(event)

    async def _execute(
        self, task: Task, message: Message, push_config: TaskPushNotificationConfig | None
    ) -> Task:
        if push_config is not None:
            self.push_configs.put(task.id, push_config.model_copy(update={"task_id": task.id}))

        working = task.model_copy(update={"status": TaskStatus(state=TaskState.WORKING)})
        await self._put_and_notify(
            working,
            StreamResponse(
                status_update=TaskStatusUpdateEvent(
                    task_id=task.id, context_id=task.context_id or "", status=working.status
                )
            ),
        )

        try:
            parts = await self.handler(message)
        except Exception as exc:  # noqa: BLE001 — reported as a failed Task, not swallowed
            reply = Message(
                context_id=task.context_id,
                task_id=task.id,
                role=Role.AGENT,
                parts=[Part.of_text(str(exc))],
            )
            failed = working.model_copy(
                update={"status": TaskStatus(state=TaskState.FAILED, message=reply)}
            )
            await self._put_and_notify(
                failed,
                StreamResponse(
                    status_update=TaskStatusUpdateEvent(
                        task_id=task.id, context_id=task.context_id or "", status=failed.status
                    )
                ),
            )
            return failed

        artifact = Artifact(name="result", parts=parts)
        await self._put_and_notify(
            working,
            StreamResponse(
                artifact_update=TaskArtifactUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id or "",
                    artifact=artifact,
                    last_chunk=True,
                )
            ),
        )
        completed = working.model_copy(
            update={"status": TaskStatus(state=TaskState.COMPLETED), "artifacts": [artifact]}
        )
        await self._put_and_notify(
            completed,
            StreamResponse(
                status_update=TaskStatusUpdateEvent(
                    task_id=task.id, context_id=task.context_id or "", status=completed.status
                )
            ),
        )
        return completed

    def _spawn(
        self, task: Task, message: Message, push_config: TaskPushNotificationConfig | None
    ) -> asyncio.Task:
        background = asyncio.create_task(self._execute(task, message, push_config))
        self._background.add(background)
        background.add_done_callback(self._background.discard)
        return background

    async def run(
        self,
        message: Message,
        push_config: TaskPushNotificationConfig | None = None,
        return_immediately: bool = False,
    ) -> Task:
        task = Task(
            context_id=message.context_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            history=[message],
        )
        self.tasks.put(task)
        background = self._spawn(task, message, push_config)
        if return_immediately:
            return task
        return await background

    async def stream(self, message: Message) -> AsyncIterator[StreamResponse]:
        """A fresh task, streamed from creation — combines `run()`'s task
        creation with `subscribe()`'s fan-out so the very first frame
        (the `SUBMITTED` task itself) is never missed to a race.
        """
        task = Task(
            context_id=message.context_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            history=[message],
        )
        self.tasks.put(task)
        queue: asyncio.Queue[StreamResponse] = asyncio.Queue()
        self._subscribers.setdefault(task.id, []).append(queue)
        await queue.put(StreamResponse(task=task))

        background = self._spawn(task, message, None)
        try:
            async for event in _drain_until_terminal(queue):
                yield event
        finally:
            self._subscribers[task.id].remove(queue)
        await background

    async def subscribe(self, task_id: str) -> AsyncIterator[StreamResponse]:
        """Attach to a task a *different* call already started (created via
        `run(..., return_immediately=True)`). Per spec, only valid while
        the task is not yet in a terminal state.
        """
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task.status.state.is_terminal:
            raise TaskAlreadyTerminalError(task_id)

        queue: asyncio.Queue[StreamResponse] = asyncio.Queue()
        self._subscribers.setdefault(task_id, []).append(queue)
        try:
            async for event in _drain_until_terminal(queue):
                yield event
        finally:
            self._subscribers[task_id].remove(queue)


async def _drain_until_terminal(
    queue: asyncio.Queue[StreamResponse],
) -> AsyncIterator[StreamResponse]:
    while True:
        event = await queue.get()
        yield event
        state = None
        if event.status_update is not None:
            state = event.status_update.status.state
        elif event.task is not None:
            state = event.task.status.state
        if state is not None and state.is_terminal:
            return

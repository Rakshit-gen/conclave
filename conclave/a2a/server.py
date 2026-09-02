"""Exposes a single local agent over the A2A HTTP+JSON REST binding.

Route table mirrors docs/a2a-spec-notes.md exactly. An `AgentHandler` is
the only thing a caller has to supply: given the incoming `Message`, return
the `Part`s of its answer (or raise, for a failed task).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException
from sse_starlette.sse import EventSourceResponse

from .models import (
    AgentCard,
    Artifact,
    Message,
    Part,
    Role,
    SendMessageRequest,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from .tasks import InMemoryTaskStore, TaskStore

AgentHandler = Callable[[Message], Awaitable[list[Part]]]


class AgentServer:
    """One agent, one FastAPI app. `handler` does the actual work; everything
    else here is A2A lifecycle bookkeeping (task states, artifacts, SSE).
    """

    def __init__(self, card: AgentCard, handler: AgentHandler, task_store: TaskStore | None = None):
        self.card = card
        self.handler = handler
        self.tasks: TaskStore = task_store or InMemoryTaskStore()
        self.app = FastAPI(title=card.name)
        self._mount_routes()

    def _mount_routes(self) -> None:
        app = self.app

        @app.get("/.well-known/agent-card.json")
        async def get_agent_card() -> dict:
            return self.card.model_dump(by_alias=True, exclude_none=True)

        @app.post("/message:send")
        async def send_message(request: SendMessageRequest) -> dict:
            task = await self._run_task(request.message)
            return task.model_dump(by_alias=True, exclude_none=True)

        @app.post("/message:stream")
        async def send_message_stream(request: SendMessageRequest) -> EventSourceResponse:
            return EventSourceResponse(self._stream_task(request.message))

        @app.get("/tasks/{task_id}")
        async def get_task(task_id: str) -> dict:
            task = self.tasks.get(task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"no such task {task_id!r}")
            return task.model_dump(by_alias=True, exclude_none=True)

        @app.get("/tasks")
        async def list_tasks() -> dict:
            tasks = self.tasks.list()
            return {"tasks": [t.model_dump(by_alias=True, exclude_none=True) for t in tasks]}

        @app.post("/tasks/{task_id}:cancel")
        async def cancel_task(task_id: str) -> dict:
            task = self.tasks.get(task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"no such task {task_id!r}")
            if not task.status.state.is_terminal:
                task = task.model_copy(update={"status": TaskStatus(state=TaskState.CANCELED)})
                self.tasks.put(task)
            return task.model_dump(by_alias=True, exclude_none=True)

    async def _run_task(self, message: Message) -> Task:
        task = Task(
            context_id=message.context_id,
            status=TaskStatus(state=TaskState.WORKING),
            history=[message],
        )
        self.tasks.put(task)
        try:
            parts = await self.handler(message)
        except Exception as exc:  # noqa: BLE001 — reported as a failed Task, not swallowed
            reply = Message(
                context_id=task.context_id,
                task_id=task.id,
                role=Role.AGENT,
                parts=[Part.of_text(str(exc))],
            )
            task = task.model_copy(
                update={"status": TaskStatus(state=TaskState.FAILED, message=reply)}
            )
            self.tasks.put(task)
            return task

        artifact = Artifact(name="result", parts=parts)
        task = task.model_copy(
            update={
                "status": TaskStatus(state=TaskState.COMPLETED),
                "artifacts": [artifact],
            }
        )
        self.tasks.put(task)
        return task

    async def _stream_task(self, message: Message):
        task = Task(
            context_id=message.context_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            history=[message],
        )
        self.tasks.put(task)
        yield _frame(StreamResponse(task=task))

        working = task.model_copy(update={"status": TaskStatus(state=TaskState.WORKING)})
        self.tasks.put(working)
        yield _frame(
            StreamResponse(
                status_update=TaskStatusUpdateEvent(
                    task_id=task.id, context_id=task.context_id or "", status=working.status
                )
            )
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
            self.tasks.put(failed)
            yield _frame(
                StreamResponse(
                    status_update=TaskStatusUpdateEvent(
                        task_id=task.id, context_id=task.context_id or "", status=failed.status
                    )
                )
            )
            return

        artifact = Artifact(name="result", parts=parts)
        yield _frame(
            StreamResponse(
                artifact_update=TaskArtifactUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id or "",
                    artifact=artifact,
                    last_chunk=True,
                )
            )
        )
        completed = working.model_copy(
            update={"status": TaskStatus(state=TaskState.COMPLETED), "artifacts": [artifact]}
        )
        self.tasks.put(completed)
        yield _frame(
            StreamResponse(
                status_update=TaskStatusUpdateEvent(
                    task_id=task.id, context_id=task.context_id or "", status=completed.status
                )
            )
        )


def _frame(response: StreamResponse) -> dict:
    return {"data": json.dumps(response.model_dump(mode="json", by_alias=True, exclude_none=True))}

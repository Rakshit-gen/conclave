"""Drives workflow functions against an event store: start, resume after a
crash, and deliver signals. This is the only place that decides when a
workflow function actually gets called.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .events import Event, EventType
from .execution import WorkflowContext, WorkflowResult, WorkflowSuspended, _current_ctx
from .store import EventStore

WorkflowFn = Callable[[Any], Awaitable[Any]]


class WorkflowNotFoundError(LookupError):
    pass


class WorkflowAlreadyStartedError(RuntimeError):
    pass


class NotSuspendedError(RuntimeError):
    """Raised by `signal()` when the workflow isn't actually waiting on that signal."""


class Runtime:
    def __init__(self, store: EventStore):
        self.store = store
        self._registry: dict[str, WorkflowFn] = {}

    def register(self, name: str, fn: WorkflowFn) -> None:
        self._registry[name] = fn

    def status(self, workflow_id: str) -> WorkflowResult | None:
        """Derive current status by scanning the log — no workflow code runs."""
        events = self.store.read(workflow_id)
        if not events:
            return None
        waiting_on: str | None = None
        for event in events:
            if event.type == EventType.WORKFLOW_SUSPENDED:
                waiting_on = event.data["name"]
            elif event.type == EventType.SIGNAL_RECEIVED and event.data["name"] == waiting_on:
                waiting_on = None
            elif event.type == EventType.WORKFLOW_COMPLETED:
                return WorkflowResult(status="completed", value=event.data["result"])
            elif event.type == EventType.WORKFLOW_FAILED:
                return WorkflowResult(status="failed", error=event.data["error"])
        if waiting_on is not None:
            return WorkflowResult(status="suspended", waiting_on=waiting_on)
        return WorkflowResult(status="running")

    async def start(
        self, workflow_name: str, workflow_id: str, input_: Any = None
    ) -> WorkflowResult:
        if self.store.read(workflow_id):
            raise WorkflowAlreadyStartedError(workflow_id)
        self.store.append(
            workflow_id,
            EventType.WORKFLOW_STARTED,
            {"workflow_name": workflow_name, "input": input_},
        )
        return await self._drive(workflow_id)

    async def resume(self, workflow_id: str) -> WorkflowResult:
        """Re-run from the top, fast-forwarding through recorded events —
        the only recovery path there is, and it's the same path a healthy
        process takes after any signal too.
        """
        events = self.store.read(workflow_id)
        if not events:
            raise WorkflowNotFoundError(workflow_id)
        current = self.status(workflow_id)
        if current is not None and current.status in ("completed", "failed"):
            return current
        return await self._drive(workflow_id)

    async def signal(self, workflow_id: str, name: str, payload: Any = None) -> WorkflowResult:
        current = self.status(workflow_id)
        if current is None:
            raise WorkflowNotFoundError(workflow_id)
        if current.status != "suspended" or current.waiting_on != name:
            raise NotSuspendedError(
                f"workflow {workflow_id!r} is not suspended on signal {name!r} "
                f"(status={current.status!r}, waiting_on={current.waiting_on!r})"
            )
        self.store.append(
            workflow_id, EventType.SIGNAL_RECEIVED, {"name": name, "payload": payload}
        )
        return await self.resume(workflow_id)

    async def _drive(self, workflow_id: str) -> WorkflowResult:
        events = self.store.read(workflow_id)
        started: Event = events[0]
        fn = self._registry.get(started.data["workflow_name"])
        if fn is None:
            raise WorkflowNotFoundError(started.data["workflow_name"])

        ctx = WorkflowContext(workflow_id, events[1:], self.store)
        token = _current_ctx.set(ctx)
        try:
            result = await fn(started.data["input"])
        except WorkflowSuspended as suspended:
            return WorkflowResult(status="suspended", waiting_on=suspended.signal_name)
        except Exception as exc:  # noqa: BLE001 — recorded as durable failure, not swallowed
            self.store.append(workflow_id, EventType.WORKFLOW_FAILED, {"error": str(exc)})
            return WorkflowResult(status="failed", error=str(exc))
        else:
            self.store.append(workflow_id, EventType.WORKFLOW_COMPLETED, {"result": result})
            return WorkflowResult(status="completed", value=result)
        finally:
            _current_ctx.reset(token)

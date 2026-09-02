"""The replay engine.

A workflow is a plain async function. To make it durable without a
sandboxed language runtime, conclave uses the same core trick real durable
execution engines do: **the entire workflow function is re-run from the
top on every drive**, but every side-effecting call goes through `step()`
or `wait_for_signal()`, which check a cursor into the recorded event log
before doing anything real. Already-recorded steps return their stored
result instantly (no side effect happens again); the first call with
nothing recorded yet is the "live" one — it actually runs, and its outcome
is durably appended before the function is allowed to continue.

This means a workflow function must be deterministic: given the same
sequence of step results, it must make the same sequence of step calls
every time it's replayed. Non-determinism (branching on `random()`,
`datetime.now()`, dict iteration order of an unordered structure) will
either silently desync the replay or trip `NonDeterminismError`. Use
`ctx.now()` instead of `datetime.now()` for exactly this reason.
"""

from __future__ import annotations

import contextvars
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from .events import Event, EventType
from .store import EventStore

T = TypeVar("T")


class WorkflowSuspended(Exception):
    """Unwinds a workflow function when it parks on `wait_for_signal`.

    Not an error — this is how a workflow "returns control" without
    blocking a thread. The Runtime catches it and reports the workflow as
    suspended; nothing about the process needs to stay alive waiting.
    """

    def __init__(self, signal_name: str):
        self.signal_name = signal_name
        super().__init__(f"suspended waiting for signal {signal_name!r}")


class StepError(Exception):
    """Raised inside workflow code when a replayed step's recorded outcome was a failure."""


class NonDeterminismError(RuntimeError):
    """The workflow function called something different than what replay expected.

    Means the workflow's code changed in a way that isn't safe across an
    in-flight run — see `get_version` for the documented escape hatch.
    """


_current_ctx: contextvars.ContextVar[WorkflowContext] = contextvars.ContextVar("conclave_ctx")


class WorkflowContext:
    """Per-drive cursor over a workflow's recorded step history, plus the
    live path for recording whatever's new this time.
    """

    def __init__(self, workflow_id: str, step_events: list[Event], store: EventStore):
        self.workflow_id = workflow_id
        self._events = step_events
        self._cursor = 0
        self._store = store

    @property
    def is_replaying(self) -> bool:
        return self._cursor < len(self._events)

    def _next_recorded(self) -> Event | None:
        if self._cursor < len(self._events):
            event = self._events[self._cursor]
            self._cursor += 1
            return event
        return None

    def _record(self, type_: EventType, data: dict[str, Any]) -> Event:
        return self._store.append(self.workflow_id, type_, data)

    async def now(self) -> datetime:
        """Deterministic wall-clock read: recorded once, replayed as a constant."""
        return await step(_read_clock, name="__now__")


async def _read_clock() -> str:
    return datetime.now(UTC).isoformat()


def current_context() -> WorkflowContext:
    try:
        return _current_ctx.get()
    except LookupError as exc:
        raise RuntimeError("step()/wait_for_signal() called outside a running workflow") from exc


async def step(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    name: str | None = None,
    **kwargs: Any,
) -> T:
    """Run (or replay) one durable side-effecting call.

    `fn`'s result must be JSON-serializable — it's persisted verbatim so
    replay can hand it back without calling `fn` again.
    """
    ctx = current_context()
    step_name = name or getattr(fn, "__name__", "step")
    recorded = ctx._next_recorded()

    if recorded is not None:
        if recorded.type == EventType.STEP_COMPLETED and recorded.data.get("name") == step_name:
            return recorded.data["result"]  # type: ignore[no-any-return]
        if recorded.type == EventType.STEP_FAILED and recorded.data.get("name") == step_name:
            raise StepError(recorded.data["error"])
        raise NonDeterminismError(
            f"replay mismatch at seq {recorded.seq}: recorded "
            f"{recorded.type.value}({recorded.data.get('name')!r}), "
            f"but code called step {step_name!r} this time"
        )

    # Nothing recorded for this point yet — this is the live edge of history.
    try:
        raw_result = fn(*args, **kwargs)
        result = await raw_result if hasattr(raw_result, "__await__") else raw_result
    except StepError:
        raise
    except Exception as exc:  # noqa: BLE001 — deliberately captured as durable failure data
        ctx._record(EventType.STEP_FAILED, {"name": step_name, "error": str(exc)})
        raise StepError(str(exc)) from exc
    ctx._record(EventType.STEP_COMPLETED, {"name": step_name, "result": result})
    return result


async def wait_for_signal(name: str) -> Any:
    """Durably suspend until `Runtime.signal(workflow_id, name, payload)` is called.

    Safe across a crash: if the process dies while suspended, `resume()`
    replays up to this exact point and suspends again, rather than losing
    track of what it was waiting for.
    """
    ctx = current_context()
    recorded = ctx._next_recorded()

    if recorded is not None:
        if recorded.type == EventType.SIGNAL_RECEIVED and recorded.data.get("name") == name:
            return recorded.data["payload"]
        if recorded.type == EventType.WORKFLOW_SUSPENDED and recorded.data.get("name") == name:
            # The suspension marker itself doesn't tell us whether the
            # signal has since arrived — that's the *next* event, if any.
            followup = ctx._next_recorded()
            if followup is None:
                raise WorkflowSuspended(name)  # still waiting — nothing new happened
            if followup.type == EventType.SIGNAL_RECEIVED and followup.data.get("name") == name:
                return followup.data["payload"]
            raise NonDeterminismError(
                f"replay mismatch at seq {followup.seq}: expected the signal {name!r} "
                f"that resolved this suspension, found {followup.type.value} instead"
            )
        raise NonDeterminismError(
            f"replay mismatch at seq {recorded.seq}: recorded {recorded.type.value}, "
            f"but code is waiting on signal {name!r} this time"
        )

    ctx._record(EventType.WORKFLOW_SUSPENDED, {"name": name})
    raise WorkflowSuspended(name)


async def get_version(change_id: str, *, max_supported: int) -> int:
    """Temporal calls this `patched`/`GetVersion`: lets a workflow's code
    change its step sequence across a deploy without breaking replay of
    runs already in flight under the old code. First live execution
    records `max_supported`; replays of history recorded before this
    change point never reach this call at all (old code didn't have it) —
    replays recorded *after* the change point get back whatever version
    was live when they were first recorded, frozen for that run's lifetime.
    """
    return await step(lambda: max_supported, name=f"__version__:{change_id}")


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    status: str  # "completed" | "failed" | "suspended"
    value: Any = None
    error: str | None = None
    waiting_on: str | None = None

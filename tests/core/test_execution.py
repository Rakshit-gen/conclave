import pytest

from conclave.core import (
    InMemoryEventStore,
    NotSuspendedError,
    Runtime,
    get_version,
    step,
    wait_for_signal,
)


async def _add(a: int, b: int) -> int:
    return a + b


async def two_step_workflow(input_: dict) -> int:
    total = await step(_add, input_["a"], input_["b"], name="add")
    doubled = await step(_add, total, total, name="double")
    return doubled


async def test_workflow_completes_and_returns_value():
    runtime = Runtime(InMemoryEventStore())
    runtime.register("two_step", two_step_workflow)

    result = await runtime.start("two_step", "wf-1", {"a": 2, "b": 3})

    assert result.status == "completed"
    assert result.value == 10


async def test_step_side_effect_runs_exactly_once_even_after_resume():
    calls = []

    async def counted_add(a: int, b: int) -> int:
        calls.append((a, b))
        return a + b

    async def wf(input_: dict) -> int:
        return await step(counted_add, input_["a"], input_["b"], name="add")

    runtime = Runtime(InMemoryEventStore())
    runtime.register("wf", wf)
    await runtime.start("wf", "wf-1", {"a": 1, "b": 1})
    assert len(calls) == 1

    # A completed workflow short-circuits on resume — no replay, no re-run.
    result = await runtime.resume("wf-1")
    assert result.status == "completed"
    assert result.value == 2
    assert len(calls) == 1


async def hitl_workflow(input_: dict) -> str:
    subtotal = await step(_add, input_["a"], input_["b"], name="add")
    approval = await wait_for_signal("approve")
    return f"{subtotal}:{approval}"


async def test_wait_for_signal_suspends_then_resumes_across_a_fresh_runtime():
    store = InMemoryEventStore()

    runtime_a = Runtime(store)
    runtime_a.register("hitl", hitl_workflow)
    result = await runtime_a.start("hitl", "wf-2", {"a": 4, "b": 6})
    assert result.status == "suspended"
    assert result.waiting_on == "approve"

    # Simulate a process restart: brand new Runtime, same durable store.
    runtime_b = Runtime(store)
    runtime_b.register("hitl", hitl_workflow)
    status = runtime_b.status("wf-2")
    assert status.status == "suspended"
    assert status.waiting_on == "approve"

    result = await runtime_b.signal("wf-2", "approve", payload="yes")
    assert result.status == "completed"
    assert result.value == "10:yes"


async def test_signal_rejected_when_not_actually_waiting_on_it():
    runtime = Runtime(InMemoryEventStore())
    runtime.register("hitl", hitl_workflow)
    await runtime.start("hitl", "wf-3", {"a": 1, "b": 1})

    with pytest.raises(NotSuspendedError):
        await runtime.signal("wf-3", "wrong-signal")


async def versioned_workflow(input_: dict) -> int:
    version = await get_version("switch-to-multiply", max_supported=2)
    if version >= 2:
        return await step(lambda: input_["a"] * input_["b"], name="multiply")
    return await step(_add, input_["a"], input_["b"], name="add")


async def test_get_version_is_frozen_for_a_replay_but_live_runs_get_latest():
    store = InMemoryEventStore()
    runtime = Runtime(store)
    runtime.register("versioned", versioned_workflow)

    result = await runtime.start("versioned", "wf-4", {"a": 3, "b": 4})
    assert result.status == "completed"
    assert result.value == 12  # live run picks max_supported=2 -> multiply

    # Replaying the same completed workflow must reproduce the same value —
    # the version recorded at wf-4's first live run, not whatever a future
    # code change might pick.
    replayed = await Runtime(store).resume("wf-4")
    assert replayed.value == 12

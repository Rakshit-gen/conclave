"""Crash recovery, proven against a real file on disk, not just in-memory
mocks — a fresh process opening the same SQLite file is what actually
happens after a kill -9, and that's what this test does.
"""

from conclave.core import Runtime, SQLiteEventStore, step, wait_for_signal


async def _fetch(x: int) -> int:
    return x * 10


async def pipeline(input_: dict) -> str:
    fetched = await step(_fetch, input_["n"], name="fetch")
    approval = await wait_for_signal("go")
    return f"{fetched}-{approval}"


async def test_sqlite_backed_workflow_survives_a_simulated_process_restart(tmp_path):
    db_path = tmp_path / "conclave.db"

    store_a = SQLiteEventStore(db_path)
    runtime_a = Runtime(store_a)
    runtime_a.register("pipeline", pipeline)
    result = await runtime_a.start("pipeline", "wf-crash", {"n": 5})
    assert result.status == "suspended"
    store_a.close()

    # Fresh store handle on the same file — nothing carried over from runtime_a.
    store_b = SQLiteEventStore(db_path)
    runtime_b = Runtime(store_b)
    runtime_b.register("pipeline", pipeline)
    result = await runtime_b.signal("wf-crash", "go", payload="ok")

    assert result.status == "completed"
    assert result.value == "50-ok"


async def different_step_name_workflow(input_: dict) -> int:
    # Deliberately calls a differently-named step than `pipeline` did at the
    # same position, to trigger a replay mismatch.
    return await step(_fetch, input_["n"], name="fetch_renamed")


async def test_replay_mismatch_is_caught_as_nondeterminism_not_silently_wrong(tmp_path):
    db_path = tmp_path / "conclave.db"
    store = SQLiteEventStore(db_path)
    runtime = Runtime(store)
    runtime.register("pipeline", pipeline)
    await runtime.start("pipeline", "wf-mismatch", {"n": 5})  # suspends after "fetch"
    store.close()

    # Same workflow name, but the registered function now takes a different
    # step path — simulates a bad, non-version-gated code change deployed
    # while wf-mismatch was still in flight.
    store2 = SQLiteEventStore(db_path)
    runtime2 = Runtime(store2)
    runtime2.register("pipeline", different_step_name_workflow)

    result = await runtime2.resume("wf-mismatch")
    assert result.status == "failed"
    assert "replay mismatch" in result.error

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx
from typer.testing import CliRunner

from conclave.cli import app
from conclave.core import Runtime, SQLiteEventStore, step

REPO_ROOT = Path(__file__).resolve().parents[1]

runner = CliRunner()


async def _add(a: int, b: int) -> int:
    return a + b


async def two_step_workflow(input_: dict) -> int:
    total = await step(_add, input_["a"], input_["b"], name="add")
    return await step(_add, total, 1, name="increment")


def _seed_db(tmp_path):
    db_path = tmp_path / "conclave.db"
    store = SQLiteEventStore(db_path)
    runtime = Runtime(store)
    runtime.register("two_step", two_step_workflow)
    asyncio.run(runtime.start("two_step", "wf-cli", {"a": 2, "b": 3}))
    store.close()
    return db_path


def test_status_reports_a_completed_workflow(tmp_path):
    db_path = _seed_db(tmp_path)

    result = runner.invoke(app, ["status", "wf-cli", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "status: completed" in result.stdout
    assert "6" in result.stdout


def test_status_exits_nonzero_for_unknown_workflow(tmp_path):
    db_path = tmp_path / "empty.db"

    result = runner.invoke(app, ["status", "does-not-exist", "--db", str(db_path)])

    assert result.exit_code == 1


def test_history_lists_every_recorded_event_in_order(tmp_path):
    db_path = _seed_db(tmp_path)

    result = runner.invoke(app, ["history", "wf-cli", "--db", str(db_path)])

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 4  # STARTED, STEP add, STEP increment, COMPLETED
    assert "WORKFLOW_STARTED" in lines[0]
    assert "WORKFLOW_COMPLETED" in lines[-1]


def test_list_shows_every_workflow_id_in_the_store(tmp_path):
    db_path = tmp_path / "conclave.db"
    store = SQLiteEventStore(db_path)
    runtime = Runtime(store)
    runtime.register("two_step", two_step_workflow)

    asyncio.run(runtime.start("two_step", "wf-a", {"a": 1, "b": 1}))
    asyncio.run(runtime.start("two_step", "wf-b", {"a": 2, "b": 2}))
    store.close()

    result = runner.invoke(app, ["list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "wf-a" in result.stdout
    assert "wf-b" in result.stdout


def test_agent_card_command_prints_the_discovered_card():
    # `CliRunner.invoke` runs the CLI's own asyncio.run() from a plain sync
    # call, so the agent under test has to be a real subprocess rather than
    # a server sharing this test's (nonexistent) event loop.
    proc = subprocess.Popen(
        [sys.executable, "-m", "examples.pipeline.serve", "researcher", "9101"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10.0
        with httpx.Client() as probe:
            card_url = "http://127.0.0.1:9101/.well-known/agent-card.json"
            while time.monotonic() < deadline:
                try:
                    if probe.get(card_url).status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("researcher agent did not become ready in time")

        result = runner.invoke(app, ["agent-card", "http://127.0.0.1:9101"])
    finally:
        proc.kill()
        proc.wait()

    assert result.exit_code == 0
    assert '"name": "Researcher"' in result.stdout

"""Drives the three-agent pipeline demo end to end.

    python -m examples.pipeline.run start "distributed consensus"
    python -m examples.pipeline.run status
    python -m examples.pipeline.run approve
    python -m examples.pipeline.run stop

To see crash recovery for real, not just assert it:

    python -m examples.pipeline.run start "distributed consensus" --crash-after write
    # exits via os._exit(137) right after "write" durably completes — a real
    # simulated kill -9, mid-workflow, not a clean return (echo $? -> 137)
    python -m examples.pipeline.run resume
    # -> suspended, waiting_on "approve_draft" — replayed research+write from
    # the log instead of re-delegating to those agents, then genuinely
    # reached (and suspended on) the point the crashed run never got to
    python -m examples.pipeline.run approve
    # -> completed — research and write still never ran twice
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from conclave.core import Runtime, SQLiteEventStore, WorkflowResult

from .config import PORTS
from .workflow import RESEARCHER_URL, REVIEWER_URL, WRITER_URL, pipeline_workflow

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_DIR = Path(__file__).parent / ".run"
DB_PATH = RUN_DIR / "conclave.db"
PIDS_PATH = RUN_DIR / "agents.json"
WORKFLOW_ID = "pipeline-demo"


def _runtime() -> Runtime:
    RUN_DIR.mkdir(exist_ok=True)
    runtime = Runtime(SQLiteEventStore(DB_PATH))
    runtime.register("pipeline", pipeline_workflow)
    return runtime


async def _wait_ready(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get(f"{url}/.well-known/agent-card.json")
                if response.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.1)
    raise RuntimeError(f"agent at {url} did not become ready within {timeout}s")


def _spawn_agents() -> None:
    RUN_DIR.mkdir(exist_ok=True)
    pids = {}
    for name, port in PORTS.items():
        log_path = RUN_DIR / f"{name}.log"
        with log_path.open("w") as log_file:
            proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell, no untrusted input
                [sys.executable, "-m", "examples.pipeline.serve", name, str(port)],
                cwd=REPO_ROOT,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        pids[name] = proc.pid
    PIDS_PATH.write_text(json.dumps(pids))


def _report(result: WorkflowResult) -> None:
    print(f"status: {result.status}")
    if result.status == "suspended":
        print(f"waiting on signal: {result.waiting_on}")
    elif result.status == "completed":
        print(json.dumps(result.value, indent=2))
    elif result.status == "failed":
        print(f"error: {result.error}")


async def _cmd_start(topic: str, crash_after: str | None) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    _spawn_agents()
    await asyncio.gather(*(_wait_ready(u) for u in (RESEARCHER_URL, WRITER_URL, REVIEWER_URL)))

    if crash_after:
        os.environ["CONCLAVE_CRASH_AFTER"] = crash_after
        print(f"starting {topic!r} (will simulate a crash right after {crash_after!r})")
    else:
        print(f"starting {topic!r}")

    result = await _runtime().start("pipeline", WORKFLOW_ID, {"topic": topic})
    _report(result)


async def _cmd_status() -> None:
    result = _runtime().status(WORKFLOW_ID)
    if result is None:
        print("no workflow started yet — run `start <topic>` first")
        return
    _report(result)


async def _cmd_resume() -> None:
    _report(await _runtime().resume(WORKFLOW_ID))


async def _cmd_approve() -> None:
    _report(await _runtime().signal(WORKFLOW_ID, "approve_draft", payload="approved"))


def _cmd_stop() -> None:
    if not PIDS_PATH.exists():
        print("no agents running")
        return
    for name, pid in json.loads(PIDS_PATH.read_text()).items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"stopped {name} (pid {pid})")
        except ProcessLookupError:
            print(f"{name} (pid {pid}) was already gone")
    PIDS_PATH.unlink()


def _cmd_reset() -> None:
    _cmd_stop()
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m examples.pipeline.run")
    sub = parser.add_subparsers(dest="command", required=True)

    start_p = sub.add_parser("start", help="spawn the three agents and start a new pipeline run")
    start_p.add_argument("topic")
    start_p.add_argument(
        "--crash-after",
        choices=["research", "write", "review"],
        default=None,
        help="simulate a kill -9 right after this step durably completes",
    )

    sub.add_parser("status", help="print the workflow's current status")
    sub.add_parser("resume", help="re-drive the workflow from its persisted history")
    sub.add_parser("approve", help="deliver the approve_draft signal")
    sub.add_parser("stop", help="stop the three agent subprocesses")
    sub.add_parser("reset", help="stop agents and wipe all demo state")

    args = parser.parse_args()
    match args.command:
        case "start":
            asyncio.run(_cmd_start(args.topic, args.crash_after))
        case "status":
            asyncio.run(_cmd_status())
        case "resume":
            asyncio.run(_cmd_resume())
        case "approve":
            asyncio.run(_cmd_approve())
        case "stop":
            _cmd_stop()
        case "reset":
            _cmd_reset()


if __name__ == "__main__":
    main()

"""Runs the actual `examples.pipeline.run` CLI as real subprocesses — three
real agent processes, a real simulated kill -9 via os._exit(137), and a
real second process resuming from the SQLite file the first one wrote.
This is slower than a unit test on purpose: it's the same sequence a
person following the README would run by hand, automated so it can't
silently rot.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "examples.pipeline.run", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_pipeline_survives_a_simulated_crash_between_two_delegations():
    _run("reset")
    try:
        crashed = _run("start", "durable execution", "--crash-after", "write", timeout=30.0)
        assert crashed.returncode == 137, crashed.stdout + crashed.stderr

        resumed = _run("resume")
        assert "status: suspended" in resumed.stdout
        assert "approve_draft" in resumed.stdout

        approved = _run("approve")
        assert "status: completed" in approved.stdout
        assert '"topic": "durable execution"' in approved.stdout
        assert "Durable execution has a well-documented history" in approved.stdout
    finally:
        _run("stop")

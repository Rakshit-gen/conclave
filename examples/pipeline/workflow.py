"""The durable workflow that ties the three demo agents together:
research -> write -> a human approval gate -> review -> done.

Every delegation is a durable step, and the approval gate is a real
`wait_for_signal` suspension — kill the orchestrating process at any point
and `conclave-pipeline resume` picks up exactly where it left off, without
re-delegating to an agent that already did its part.
"""

from __future__ import annotations

import os

from conclave.core import wait_for_signal

from .config import PORTS
from .orchestrator_helpers import delegate_text

RESEARCHER_URL = f"http://127.0.0.1:{PORTS['researcher']}"
WRITER_URL = f"http://127.0.0.1:{PORTS['writer']}"
REVIEWER_URL = f"http://127.0.0.1:{PORTS['reviewer']}"


def _maybe_crash_after(step_name: str) -> None:
    """Test/demo hook only: `CONCLAVE_CRASH_AFTER=<step>` kills this process
    right after that step durably completes, simulating a real `kill -9` mid
    workflow so crash recovery can be demonstrated honestly instead of just
    asserted. Never set outside a deliberate demo run.
    """
    if os.environ.get("CONCLAVE_CRASH_AFTER") == step_name:
        os._exit(137)  # 128 + SIGKILL, matching the real kill -9 exit code


async def pipeline_workflow(input_: dict) -> dict:
    topic = input_["topic"]

    bullets = await delegate_text(RESEARCHER_URL, topic, name="research")
    _maybe_crash_after("research")

    draft = await delegate_text(WRITER_URL, bullets, name="write")
    _maybe_crash_after("write")

    await wait_for_signal("approve_draft")

    final = await delegate_text(REVIEWER_URL, draft, name="review")
    _maybe_crash_after("review")

    return {"topic": topic, "bullets": bullets, "draft": draft, "final": final}

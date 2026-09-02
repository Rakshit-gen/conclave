"""The event vocabulary a workflow's history is built from.

Everything the durable execution engine knows about a workflow run is
whatever's in its event log — nothing is trusted from in-memory state,
because in-memory state is exactly what a crash destroys.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    SIGNAL_RECEIVED = "SIGNAL_RECEIVED"
    WORKFLOW_SUSPENDED = "WORKFLOW_SUSPENDED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"


@dataclass(frozen=True, slots=True)
class Event:
    workflow_id: str
    seq: int
    type: EventType
    data: dict[str, Any]
    recorded_at: datetime

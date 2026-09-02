"""Task storage for an A2A server.

Deliberately not durable — that's the job of the durable execution core on
the *caller* side (a delegation is recorded as a step there). This just
needs to answer GET /tasks/{id} correctly while a task is in flight.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from .models import Task


class TaskStore(ABC):
    @abstractmethod
    def put(self, task: Task) -> None: ...

    @abstractmethod
    def get(self, task_id: str) -> Task | None: ...

    @abstractmethod
    def list(self) -> list[Task]: ...


class InMemoryTaskStore(TaskStore):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}

    def put(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

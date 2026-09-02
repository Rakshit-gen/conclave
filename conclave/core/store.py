"""Durable storage for workflow event logs.

The engine only ever asks a store to append (with a server-assigned,
gap-free sequence number) or read a workflow's full ordered history. That's
the entire contract — small enough that a crash-safe SQLite implementation
is a real, not a toy, answer.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .events import Event, EventType


class EventStore(ABC):
    @abstractmethod
    def append(self, workflow_id: str, type_: EventType, data: dict[str, Any]) -> Event: ...

    @abstractmethod
    def read(self, workflow_id: str) -> list[Event]: ...

    @abstractmethod
    def list_workflow_ids(self) -> list[str]: ...


class SQLiteEventStore(EventStore):
    """One row per event, keyed by (workflow_id, seq). `seq` is assigned
    under a lock from `MAX(seq) + 1`, so it's gap-free and append-only —
    the two properties the replay engine's cursor depends on.
    """

    def __init__(self, path: str | Path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                workflow_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (workflow_id, seq)
            )
            """
        )
        self._conn.commit()

    def append(self, workflow_id: str, type_: EventType, data: dict[str, Any]) -> Event:
        recorded_at = datetime.now(UTC)
        with self._lock:
            (next_seq,) = self._conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM events WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            self._conn.execute(
                "INSERT INTO events (workflow_id, seq, type, data, recorded_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (workflow_id, next_seq, type_.value, json.dumps(data), recorded_at.isoformat()),
            )
            self._conn.commit()
        return Event(workflow_id, next_seq, type_, data, recorded_at)

    def read(self, workflow_id: str) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, type, data, recorded_at FROM events "
                "WHERE workflow_id = ? ORDER BY seq ASC",
                (workflow_id,),
            ).fetchall()
        return [
            Event(
                workflow_id,
                seq,
                EventType(type_),
                json.loads(data),
                datetime.fromisoformat(recorded_at),
            )
            for seq, type_, data, recorded_at in rows
        ]

    def list_workflow_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT DISTINCT workflow_id FROM events").fetchall()
        return [row[0] for row in rows]

    def close(self) -> None:
        self._conn.close()


class InMemoryEventStore(EventStore):
    """Same contract, no disk — for tests that want speed, not durability."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, list[Event]] = {}

    def append(self, workflow_id: str, type_: EventType, data: dict[str, Any]) -> Event:
        with self._lock:
            log = self._events.setdefault(workflow_id, [])
            event = Event(workflow_id, len(log), type_, data, datetime.now(UTC))
            log.append(event)
        return event

    def read(self, workflow_id: str) -> list[Event]:
        with self._lock:
            return list(self._events.get(workflow_id, []))

    def list_workflow_ids(self) -> list[str]:
        with self._lock:
            return list(self._events.keys())

"""Inspect a workflow's durable history, or a remote agent's Agent Card,
without writing any Python. This is also how the event-sourced core gets
reviewed as it's built — `conclave history <id>` shows exactly what's in
the log, not what the code claims is in the log.
"""

from __future__ import annotations

import asyncio
import json

import typer

from conclave.a2a import AgentClient
from conclave.core import Runtime, SQLiteEventStore

app = typer.Typer(help="Inspect conclave workflow histories and A2A agents.", no_args_is_help=True)


def _store(db: str) -> SQLiteEventStore:
    return SQLiteEventStore(db)


@app.command()
def status(workflow_id: str, db: str = "conclave.db") -> None:
    """Print a workflow's current status, derived from its event log."""
    result = Runtime(_store(db)).status(workflow_id)
    if result is None:
        typer.echo(f"no such workflow {workflow_id!r} in {db}")
        raise typer.Exit(1)
    typer.echo(f"status: {result.status}")
    if result.status == "suspended":
        typer.echo(f"waiting on: {result.waiting_on}")
    elif result.status == "completed":
        typer.echo(json.dumps(result.value, indent=2))
    elif result.status == "failed":
        typer.echo(f"error: {result.error}")


@app.command()
def history(workflow_id: str, db: str = "conclave.db") -> None:
    """Print every event recorded for a workflow, in order."""
    events = _store(db).read(workflow_id)
    if not events:
        typer.echo(f"no such workflow {workflow_id!r} in {db}")
        raise typer.Exit(1)
    for event in events:
        typer.echo(
            f"[{event.seq:>3}] {event.recorded_at.isoformat()}  "
            f"{event.type.value:<20} {json.dumps(event.data)}"
        )


@app.command(name="list")
def list_workflows(db: str = "conclave.db") -> None:
    """List every workflow id recorded in a store."""
    ids = _store(db).list_workflow_ids()
    if not ids:
        typer.echo(f"no workflows recorded in {db}")
        return
    for workflow_id in ids:
        typer.echo(workflow_id)


@app.command(name="agent-card")
def agent_card(url: str) -> None:
    """Discover and print a remote agent's Agent Card."""

    async def _fetch():
        client = AgentClient(url)
        try:
            return await client.discover()
        finally:
            await client.aclose()

    card = asyncio.run(_fetch())
    typer.echo(json.dumps(card.model_dump(by_alias=True, exclude_none=True, mode="json"), indent=2))


if __name__ == "__main__":
    app()

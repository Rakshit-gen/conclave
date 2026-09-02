# conclave

A durable multi-agent orchestrator, built from scratch.

Two things live here, and neither wraps an existing framework:

1. **A durable execution core** — event-sourced workflow state, deterministic
   replay, crash recovery, and resumable human-in-the-loop approval gates.
   Restart the process mid-workflow and it picks up exactly where it left
   off, because it never trusted memory in the first place.
2. **An A2A (Agent2Agent) protocol implementation** — agent discovery via
   Agent Cards, task lifecycle, and cross-agent delegation over the real
   wire protocol, not a mocked-up stand-in for it.

The orchestrator sits on top of both: a workflow can durably delegate a task
to a remote agent it has never talked to before, wait for the result (or a
human's approval) across a crash and restart, and keep going.

Architecture, build log, and the demo walkthrough land in `docs/` as the
project is built.

## Status

Early. See `docs/` for design notes as they're written.

## License

MIT
